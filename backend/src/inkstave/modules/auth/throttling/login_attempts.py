"""Login attempt limits: per e-mail and per IP, counting only wrong passwords.

An attempt is counted when it starts and forgiven unless the password was wrong. Counting at
the end would let a concurrent burst through: every guess passes the check while the Argon2
verifies of the others are still running.

Success clears the e-mail's counter but only forgives its own hit on the IP's. Clearing the IP
as well would let an attacker with one valid account reset the limit between guesses.

Decision: a Redis outage fails open, with a warning and a metric. Refusing logins would turn a
cache outage into a site-wide lockout; the cost is that guessing goes unthrottled meanwhile,
still slowed by Argon2.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import Depends, Request

from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import RateLimitError
from inkstave.core.observability.metrics import inc_rate_limit_error
from inkstave.modules.auth.accounts.login import InvalidCredentialsError
from inkstave.modules.auth.accounts.users import normalise_email
from inkstave.modules.auth.throttling.limiter import client_ip, hit_window, parse_rate_limit

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.core.config.settings import Settings

logger = logging.getLogger("inkstave.ratelimit")


class LoginThrottle:
    def __init__(self, redis: Redis, settings: Settings, ip: str) -> None:
        self._redis = redis
        self._enabled = settings.rate_limit_enabled
        self._ip_key = f"ratelimit:login:ip:{ip}"
        self._ip_limit = parse_rate_limit(settings.rate_limit_login_ip)
        self._email_limit = parse_rate_limit(settings.rate_limit_login)

    @staticmethod
    def _email_key(email: str) -> str:
        return f"ratelimit:login:email:{normalise_email(email)}"

    async def _check(self, key: str, limit: tuple[int, int]) -> None:
        maximum, window = limit
        count, ttl = await hit_window(self._redis, key, window)
        if count > maximum:
            raise RateLimitError(retry_after_seconds=ttl if ttl > 0 else window)

    async def _count(self, email: str) -> bool:
        """Count the attempt or raise 429; ``False`` when the counters are unreachable."""
        try:
            await self._check(self._ip_key, self._ip_limit)
            await self._check(self._email_key(email), self._email_limit)
        except RateLimitError:
            raise
        except Exception:
            self._warn()
            return False
        return True

    async def _forgive(self, email: str) -> None:
        try:
            await self._redis.delete(self._email_key(email))
            if await self._redis.decr(self._ip_key) <= 0:
                # The window may have ended meanwhile: never leave a counter without a TTL.
                await self._redis.delete(self._ip_key)
        except Exception:
            self._warn()

    @staticmethod
    def _warn() -> None:
        logger.warning("Rate limiter unavailable; allowing request (scope=login)")
        inc_rate_limit_error("login")

    @asynccontextmanager
    async def attempt(self, email: str) -> AsyncIterator[None]:
        """Guard one login; only ``InvalidCredentialsError`` leaves the attempt counted."""
        counted = self._enabled and await self._count(email)
        wrong_password = False
        try:
            yield
        except InvalidCredentialsError:
            wrong_password = True
            raise
        finally:
            if counted and not wrong_password:
                await self._forgive(email)


def get_login_throttle(
    request: Request,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings_dep),
) -> LoginThrottle:
    return LoginThrottle(redis, settings, client_ip(request, settings))


# Marker read by the guard-coverage audit (spec 55).
get_login_throttle.__rate_limit__ = "login"  # type: ignore[attr-defined]
