"""Redis-backed named-policy rate limiting (spec 52 §5.2.1).

A fixed-window counter incremented atomically with a Lua script (INCR + EXPIRE in
one round trip, no race). Applied as a FastAPI dependency; sets ``X-RateLimit-*``
headers on every response and returns 429 + ``Retry-After`` when exceeded. **Fails
open** (logs a warning + increments a metric) if Redis is unavailable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from fastapi import Depends, Request, Response
from pydantic import BaseModel
from redis.exceptions import ResponseError

from inkstave.auth.dependencies import get_optional_user
from inkstave.auth.rate_limit import client_ip
from inkstave.dependencies import get_redis, get_settings_dep
from inkstave.errors import RateLimitError
from inkstave.observability.metrics import inc_rate_limit_error

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.config import Settings
    from inkstave.db.models.user import User

logger = logging.getLogger("inkstave.ratelimit")

# One atomic round trip: increment the window counter, set its TTL on first hit,
# and return both the count and the remaining TTL.
_WINDOW_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {c, redis.call('TTL', KEYS[1])}
"""


class RateLimitPolicy(BaseModel):
    name: str
    limit: int
    window_seconds: int
    key: Literal["ip", "user", "user_or_ip"]


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset: int  # unix seconds
    retry_after: int


def policy_from_setting(name: str, value: str, key: str) -> RateLimitPolicy:
    limit_str, _, window_str = value.partition("/")
    return RateLimitPolicy(
        name=name,
        limit=int(limit_str),
        window_seconds=int(window_str),
        key=key,  # type: ignore[arg-type]
    )


async def check_rate_limit(
    redis: Redis, policy: RateLimitPolicy, scope_id: str, *, now: float
) -> RateLimitResult:
    key = f"rl:{policy.name}:{scope_id}"
    try:
        count, ttl = await redis.eval(  # type: ignore[misc]
            _WINDOW_LUA, 1, key, str(policy.window_seconds)
        )
    except ResponseError:
        # Backend without server-side scripting (e.g. fakeredis): two-step fallback.
        count = await redis.incr(key)
        if int(count) == 1:
            await redis.expire(key, policy.window_seconds)
        ttl = await redis.ttl(key)
    ttl_s = int(ttl) if ttl and int(ttl) > 0 else policy.window_seconds
    remaining = max(0, policy.limit - int(count))
    return RateLimitResult(
        allowed=int(count) <= policy.limit,
        limit=policy.limit,
        remaining=remaining,
        reset=int(now) + ttl_s,
        retry_after=ttl_s,
    )


def _set_headers(response: Response, result: RateLimitResult) -> None:
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset)


# name → (settings attribute, key strategy) for the hardened per-user policies.
_NAMED_POLICIES: dict[str, tuple[str, str]] = {
    "compile": ("rate_limit_compile", "user"),
    "agent": ("rate_limit_agent", "user"),
    "upload": ("rate_limit_upload", "user"),
}


async def _enforce(
    redis: Redis,
    response: Response,
    request: Request,
    user: User | None,
    settings: Settings,
    policy: RateLimitPolicy,
) -> None:
    scope_id = _scope_id(policy, request, user, settings)
    try:
        result = await check_rate_limit(redis, policy, scope_id, now=time.time())
    except Exception:
        # Fail open — a limiter outage must not lock out legitimate traffic.
        logger.warning("rate_limit_backend_unavailable (policy=%s)", policy.name)
        inc_rate_limit_error(policy.name)
        return
    _set_headers(response, result)
    if not result.allowed:
        raise RateLimitError(
            result.retry_after, limit=result.limit, remaining=0, reset=result.reset
        )


def rate_limit(policy: RateLimitPolicy) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency enforcing a fixed ``policy``."""

    async def dependency(
        request: Request,
        response: Response,
        user: User | None = Depends(get_optional_user),
        redis: Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        await _enforce(redis, response, request, user, settings, policy)

    dependency.__rate_limit__ = policy.name  # type: ignore[attr-defined]
    return dependency


def rate_limit_named(name: str) -> Callable[..., Awaitable[None]]:
    """Build a dependency for a named policy whose limit is read from settings."""
    attr, key = _NAMED_POLICIES[name]

    async def dependency(
        request: Request,
        response: Response,
        user: User | None = Depends(get_optional_user),
        redis: Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        policy = policy_from_setting(name, getattr(settings, attr), key)
        await _enforce(redis, response, request, user, settings, policy)

    dependency.__rate_limit__ = name  # type: ignore[attr-defined]
    return dependency


def _scope_id(
    policy: RateLimitPolicy, request: Request, user: User | None, settings: Settings
) -> str:
    ip = client_ip(request, settings) if settings.trust_proxy_headers else _raw_ip(request)
    if policy.key == "ip":
        return ip
    if policy.key == "user":
        return f"user:{user.id}" if user is not None else f"ip:{ip}"
    return f"user:{user.id}" if user is not None else f"ip:{ip}"  # user_or_ip


def _raw_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
