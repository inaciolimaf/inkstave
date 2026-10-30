"""Domain-free FastAPI dependencies: configuration and the shared Redis connection.

Settings come from the cached accessor; connections live on ``app.state`` and are created
once in the lifespan, never per request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from inkstave.core.config.settings import Settings, get_settings
from inkstave.core.errors import AppError

if TYPE_CHECKING:
    from redis.asyncio import Redis


class ServiceUnavailableError(AppError):
    """Raised when a required backing service connection is missing."""

    status_code = 503
    error_type = "service_unavailable"


def get_settings_dep() -> Settings:
    """Dependency returning the cached :class:`~inkstave.core.config.settings.Settings`."""
    return get_settings()


def get_redis(request: Request) -> Redis:
    """Dependency returning the shared Redis client from ``app.state``."""
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise ServiceUnavailableError("Redis connection is not available")
    return redis
