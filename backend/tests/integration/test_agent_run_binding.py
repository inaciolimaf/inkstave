"""Integration: an agent run is reachable only through the session it belongs to (spec 44)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.agent.models import AgentRunState, AgentSession
from inkstave.modules.agent.runs.events import cancel_key
from inkstave.modules.agent.safety import AuditSubject, audit
from inkstave.modules.agent.safety.models import AgentAuditAction

from ._agent_api_support import API, _FakeEnqueuer, enqueuer, seed

__all__ = ["enqueuer", "seed"]

pytestmark = pytest.mark.integration


async def _new_session(async_client: AsyncClient, base: str, headers: dict[str, str]) -> str:
    r = await async_client.post(f"{base}/sessions", json={}, headers=headers)
    return str(r.json()["id"])


async def _post(async_client: AsyncClient, base: str, sid: str, headers: dict[str, str]) -> UUID:
    r = await async_client.post(f"{base}/sessions/{sid}/messages", json={"content": "hi"}, headers=headers)
    assert r.status_code == 202
    return UUID(r.json()["run_id"])


async def test_cancel_and_events_of_another_sessions_run_are_404(
    seed: SimpleNamespace, async_client: AsyncClient, enqueuer: _FakeEnqueuer, redis: Any
) -> None:
    base = f"{API}/{seed.project.id}/agent"
    sid_a = await _new_session(async_client, base, seed.headers)
    sid_b = await _new_session(async_client, base, seed.headers)
    run_b = await _post(async_client, base, sid_b, seed.headers)

    # The run exists, but it is session B's: session A's path must not reach it.
    cancel = await async_client.post(f"{base}/sessions/{sid_a}/runs/{run_b}/cancel", headers=seed.headers)
    assert cancel.status_code == 404
    assert not await redis.exists(cancel_key(run_b))  # the cancel flag was never set

    events = await async_client.get(f"{base}/sessions/{sid_a}/runs/{run_b}/events", headers=seed.headers)
    assert events.status_code == 404


async def test_cancel_of_an_unknown_run_is_404(
    seed: SimpleNamespace, async_client: AsyncClient, redis: Any
) -> None:
    base = f"{API}/{seed.project.id}/agent"
    sid = await _new_session(async_client, base, seed.headers)
    unknown = uuid4()

    r = await async_client.post(f"{base}/sessions/{sid}/runs/{unknown}/cancel", headers=seed.headers)
    assert r.status_code == 404
    assert not await redis.exists(cancel_key(unknown))


async def test_a_finished_run_of_the_session_stays_reachable(
    seed: SimpleNamespace,
    async_client: AsyncClient,
    db_session: AsyncSession,
    enqueuer: _FakeEnqueuer,
) -> None:
    """A run that is no longer the active one still belongs to its session (its audit rows say so)."""
    base = f"{API}/{seed.project.id}/agent"
    sid = await _new_session(async_client, base, seed.headers)
    run = await _post(async_client, base, sid, seed.headers)

    # The turn finished: its audit rows name the session, and the session is no longer active.
    await audit(
        db_session,
        AgentAuditAction.run_stop,
        AuditSubject(seed.owner.id, seed.project.id, UUID(sid), run),
        outcome="ok",
    )
    row = await db_session.get(AgentSession, UUID(sid))
    assert row is not None
    row.active_run_id = None
    row.run_state = AgentRunState.done.value
    await db_session.commit()

    r = await async_client.post(f"{base}/sessions/{sid}/runs/{run}/cancel", headers=seed.headers)
    assert r.status_code == 202
