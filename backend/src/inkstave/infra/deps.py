"""FastAPI dependencies for the technical services (object store, email queue)."""

from __future__ import annotations

from fastapi import Depends, Request

from inkstave.core.config.settings import Settings
from inkstave.core.deps import get_settings_dep
from inkstave.infra.mailer.enqueuer import EmailEnqueuer
from inkstave.infra.storage.base import ObjectStore
from inkstave.infra.storage.factory import get_object_store as build_object_store


def get_object_store(settings: Settings = Depends(get_settings_dep)) -> ObjectStore:
    """Dependency providing the configured object store (tests override it)."""
    return build_object_store(settings)


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
