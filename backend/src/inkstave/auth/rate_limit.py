"""Redis-backed fixed-window rate limiting (spec 08 groundwork).

A ``rate_limit(scope)`` factory returns a FastAPI dependency that throttles a
route by client identity. It **fails open**: if Redis errors, the request is
allowed and a warning is logged, so a limiter outage cannot lock everyone out.
Full hardening (sliding windows, abuse heuristics) is spec 52.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from redis.exceptions import ResponseError

from inkstave.config import Settings
from inkstave.dependencies import get_redis, get_settings_dep
from inkstave.errors import RateLimitError

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("inkstave.ratelimit")

# Scopes whose identity also includes the submitted email (credential stuffing).
_EMAIL_SCOPES = {"login", "register"}
_SCOPE_SETTING = {
    "login": "rate_limit_login",
    "register": "rate_limit_register",
    "refresh": "rate_limit_refresh",
}


def parse_rate_limit(value: str) -> tuple[int, int]:
    """Parse a ``"<limit>/<window_seconds>"`` string into ``(limit, window)``."""
    limit_str, _, window_str = value.partition("/")
    return int(limit_str), int(window_str)


# One atomic round trip: increment the window counter, set its TTL on first hit,
# and return both the count and the remaining TTL (mirrors security.rate_limit so
# a concurrent burst can never leave a counter without an expiry — spec 55).
_WINDOW_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {c, redis.call('TTL', KEYS[1])}
"""


def client_ip(request: Request, settings: Settings) -> str:
    """Resolve the client IP.

    The trusted proxy header is honoured **only** when ``trust_proxy_headers`` is
    set (spec 52): otherwise a client could spoof ``X-Forwarded-For`` to dodge the
    per-IP limit. Single source of truth for IP derivation, shared by the auth and
    security limiters.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get(settings.trusted_proxy_header)
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _identity(request: Request, scope: str, settings: Settings) -> str:
    ip = client_ip(request, settings)
    if scope in _EMAIL_SCOPES:
        try:
            body = await request.json()
            email = str(body.get("email", "")).strip().lower()
        except Exception:
            # Degraded to IP-only identity — surface it (scope only, never the body).
            logger.debug("rate-limit identity: body parse failed, using ip only (scope=%s)", scope)
            email = ""
        if email:
            return f"{ip}:{email}"
    return ip


def rate_limit(scope: str) -> Callable[..., Awaitable[None]]:
    """Build a dependency that rate-limits the given ``scope``."""

    async def dependency(
        request: Request,
        redis: Redis = Depends(get_redis),
        settings: Settings = Depends(get_settings_dep),
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        limit, window = parse_rate_limit(getattr(settings, _SCOPE_SETTING[scope]))
        key = f"ratelimit:{scope}:{await _identity(request, scope, settings)}"
        try:
            try:
                count, ttl = await redis.eval(_WINDOW_LUA, 1, key, str(window))  # type: ignore[misc]
            except ResponseError:
                # Backend without server-side scripting: two-step fallback.
                count = await redis.incr(key)
                if int(count) == 1:
                    await redis.expire(key, window)
                ttl = await redis.ttl(key)
            if int(count) > limit:
                ttl_s = int(ttl) if ttl and int(ttl) > 0 else window
                raise RateLimitError(retry_after_seconds=ttl_s)
        except RateLimitError:
            raise
        except Exception:
            # Fail open: a limiter outage must not block legitimate traffic.
            logger.warning("Rate limiter unavailable; allowing request (scope=%s)", scope)

    # Marker so the guard-coverage audit (spec 55) can detect the policy on a route,
    # mirroring the authz ``__authz_capability__`` marker.
    dependency.__rate_limit__ = scope  # type: ignore[attr-defined]
    return dependency
