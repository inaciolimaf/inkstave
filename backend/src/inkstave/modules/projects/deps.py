"""FastAPI dependencies the projects module offers."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inkstave.core.config.settings import Settings
from inkstave.core.db.session import get_session_factory
from inkstave.core.deps import get_settings_dep
from inkstave.infra.deps import get_object_store
from inkstave.infra.storage.base import ObjectStore
from inkstave.modules.projects.transfer.enqueuer import ImportEnqueuer, ImportServices


async def get_import_enqueuer(
    request: Request, settings: Settings = Depends(get_settings_dep)
) -> ImportEnqueuer:
    """Dependency providing the ARQ project-import enqueuer (faked in tests).

    Shares the single ARQ pool / queue with the other jobs (one worker, spec 101).
    """
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.arq_pool = pool
    return ImportEnqueuer(pool, settings.compile_queue_name)


async def get_import_services(
    store: ObjectStore = Depends(get_object_store),
    enqueuer: ImportEnqueuer = Depends(get_import_enqueuer),
    sessions: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ImportServices:
    """The store, the enqueuer and the session factory an import request hands to its background job."""
    return ImportServices(store=store, enqueuer=enqueuer, sessions=sessions)
