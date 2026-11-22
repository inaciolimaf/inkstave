"""Liveness of an agent run (spec 44): the reaper settles a run whose worker died.

A run is alive while its progress marker exists, and every event refreshes it. A session whose
active run has no marker is stuck: the worker crashed, or the job never started. The next message
settles that run as ``timeout`` and frees the session, so a dead worker cannot block the chat.
A concurrency slot is claimed once the run starts and given back once, by the run or the reaper.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.modules.agent.models import AgentRunState
from inkstave.modules.agent.runs.events import RedisEventSink, beat_key
from inkstave.modules.agent.safety import AgentAuditAction, AuditSubject, audit, release_run

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.agent import AgentSettings
    from inkstave.modules.agent.models import AgentSession

logger = logging.getLogger("inkstave.agent.api")

# States in which a run is genuinely in flight, so a new message must wait for it or reap it.
ACTIVE_RUN_STATES = frozenset(
    {
        AgentRunState.queued.value,
        AgentRunState.running.value,
        AgentRunState.cancelling.value,
    }
)

# The concurrency counter in safety/rate_limit.py lives for the same hour.
_SLOT_TTL_S = 3600


def slot_key(run_id: UUID | str) -> str:
    return f"agent:run:{run_id}:slot"


async def claim_slot(redis: Redis, run_id: UUID) -> None:
    """Mark that this run holds one of its user's concurrency slots (``acquire_run`` counted it)."""
    await redis.set(slot_key(run_id), b"1", ex=_SLOT_TTL_S)


async def release_slot(redis: Redis, run_id: UUID, user_id: UUID) -> None:
    """Give the slot back at most once, whether the run or the reaper gets there first."""
    if await redis.delete(slot_key(run_id)):
        await release_run(redis, user_id=user_id)


async def _emit_timeout(redis: Redis, run_id: UUID, settings: AgentSettings) -> None:
    """Tell any open panel that the run stopped; a Redis failure must not block the reaping."""
    sink = RedisEventSink(redis, str(run_id), settings.agent_run_ttl_s)
    try:
        await sink.emit("error", code="timeout", message="The agent run stopped responding.")
    except Exception:
        logger.warning("could not announce the stalled agent run %s", run_id, exc_info=True)


async def reap_if_stalled(
    db: AsyncSession,
    redis: Redis,
    session: AgentSession,
    settings: AgentSettings,
) -> bool:
    """Settle the session's active run if it has gone silent. True when it was reaped."""
    run_id = session.active_run_id
    if session.run_state not in ACTIVE_RUN_STATES or run_id is None:
        return False
    if await redis.exists(beat_key(run_id)):
        return False  # progress within the stall timeout: the run is alive
    await release_slot(redis, run_id, session.user_id)
    await _emit_timeout(redis, run_id, settings)
    session.run_state = AgentRunState.error.value
    session.active_run_id = None
    subject = AuditSubject(session.user_id, session.project_id, session.id, run_id)
    await audit(db, AgentAuditAction.error, subject, outcome="error", detail={"reason": "stalled"})
    logger.warning("agent run %s stalled; settled as timeout", run_id)
    return True
