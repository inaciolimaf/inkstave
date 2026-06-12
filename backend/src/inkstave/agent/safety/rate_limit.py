"""Per-user / per-project agent run rate limiting (spec 49). Redis-backed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.agent.settings import AgentSettings


@dataclass
class RateDecision:
    allowed: bool
    retry_after: int = 0
    reason: str = ""


def _window(now: float) -> int:
    return int(now) // 60


def _user_key(user_id: UUID, window: int) -> str:
    return f"agent:rl:user:{user_id}:{window}"


def _project_key(project_id: UUID, window: int) -> str:
    return f"agent:rl:proj:{project_id}:{window}"


def _concurrency_key(user_id: UUID) -> str:
    return f"agent:conc:user:{user_id}"


async def check_rate_limit(
    redis: Redis,
    settings: AgentSettings,
    *,
    user_id: UUID,
    project_id: UUID,
    now: float,
) -> RateDecision:
    """Read-only check (a value of 0 disables that cap). Does not mutate counters."""
    window = _window(now)
    retry_after = 60 - (int(now) % 60)

    for key, limit in (
        (_user_key(user_id, window), settings.agent_max_runs_per_minute_per_user),
        (_project_key(project_id, window), settings.agent_max_runs_per_minute_per_project),
    ):
        if limit <= 0:
            continue
        current = await redis.get(key)
        if current is not None and int(current) >= limit:
            return RateDecision(False, retry_after, "rate")

    conc_limit = settings.agent_max_concurrent_runs_per_user
    if conc_limit > 0:
        active = await redis.get(_concurrency_key(user_id))
        if active is not None and int(active) >= conc_limit:
            return RateDecision(False, 5, "concurrency")

    return RateDecision(True)


async def acquire_run(
    redis: Redis, *, user_id: UUID, project_id: UUID, now: float
) -> None:
    """Record a started run: bump the per-minute windows + the concurrency counter."""
    window = _window(now)
    for key in (_user_key(user_id, window), _project_key(project_id, window)):
        await redis.incr(key)
        await redis.expire(key, 120)
    await redis.incr(_concurrency_key(user_id))
    await redis.expire(_concurrency_key(user_id), 3600)


async def release_run(redis: Redis, *, user_id: UUID) -> None:
    """Release a finished run's concurrency slot (floored at zero)."""
    key = _concurrency_key(user_id)
    current = await redis.get(key)
    if current is not None and int(current) > 0:
        await redis.decr(key)
