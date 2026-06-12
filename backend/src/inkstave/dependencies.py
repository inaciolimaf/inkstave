"""FastAPI dependency callables.

The single place feature code reaches configuration and shared connections.
Settings come from the cached accessor; connections live on ``app.state`` and
are created once in the lifespan — never per request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from inkstave.agent.api.enqueuer import AgentEnqueuer
from inkstave.auth.password import PasswordHasher, build_password_hasher
from inkstave.auth.refresh_store import RefreshStore, build_refresh_store
from inkstave.auth.tokens import TokenService, build_token_service
from inkstave.compile.enqueuer import ArqEnqueuer
from inkstave.config import Settings, get_settings
from inkstave.errors import AppError
from inkstave.mailer.enqueuer import EmailEnqueuer
from inkstave.storage.base import ObjectStore
from inkstave.storage.factory import get_object_store as build_object_store

if TYPE_CHECKING:
    from redis.asyncio import Redis


class ServiceUnavailableError(AppError):
    """Raised when a required backing service connection is missing."""

    status_code = 503
    error_type = "service_unavailable"


def get_settings_dep() -> Settings:
    """Dependency returning the cached :class:`~inkstave.config.Settings`."""
    return get_settings()


def get_redis(request: Request) -> Redis:
    """Dependency returning the shared Redis client from ``app.state``."""
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise ServiceUnavailableError("Redis connection is not available")
    return redis


def get_password_hasher(
    settings: Settings = Depends(get_settings_dep),
) -> PasswordHasher:
    """Dependency providing an argon2 password hasher built from settings."""
    return build_password_hasher(settings)


def get_token_service(
    settings: Settings = Depends(get_settings_dep),
) -> TokenService:
    """Dependency providing the JWT token service built from settings."""
    return build_token_service(settings)


def get_refresh_store(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> RefreshStore:
    """Dependency providing the Redis-backed refresh-token store."""
    return build_refresh_store(get_redis(request), settings)


def get_object_store(settings: Settings = Depends(get_settings_dep)) -> ObjectStore:
    """Dependency providing the configured object store (tests override it)."""
    return build_object_store(settings)


async def get_compile_enqueuer(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> ArqEnqueuer:
    """Dependency providing the ARQ compile enqueuer (overridden with a fake in tests).

    Lazily creates and caches a single ARQ pool on ``app.state``.
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.arq_pool = pool
    return ArqEnqueuer(pool, settings.compile_queue_name)


async def get_email_enqueuer(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> EmailEnqueuer:
    """Dependency providing the ARQ email enqueuer (faked in tests).

    Shares the single ARQ pool / queue with the other jobs (one worker, spec 39).
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.arq_pool = pool
    return EmailEnqueuer(pool, settings.compile_queue_name)


async def get_agent_enqueuer(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> AgentEnqueuer:
    """Dependency providing the ARQ agent-turn enqueuer (faked in tests)."""
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.arq_pool = pool
    return AgentEnqueuer(pool, settings.compile_queue_name)
