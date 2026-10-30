"""FastAPI dependencies the compile module offers."""

from __future__ import annotations

from fastapi import Depends, Request

from inkstave.core.config.settings import Settings
from inkstave.core.deps import get_settings_dep
from inkstave.modules.compile.queue.enqueuer import ArqEnqueuer


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
