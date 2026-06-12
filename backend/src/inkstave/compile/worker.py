"""ARQ worker bootstrap for compile jobs (spec 22).

Run with:  arq inkstave.compile.worker.WorkerSettings
Tests do NOT use this — they call ``run_compile`` directly with a hand-built ctx
and a stubbed compile service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func

from inkstave.compile.jobs import run_compile
from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.packages import load_package_config
from inkstave.compile.result import CompileResult
from inkstave.compile.retention import cleanup_compile_outputs
from inkstave.compile.runner import LocalTectonicRunner
from inkstave.compile.service import CompileService
from inkstave.compile.sources import DbDocumentSource, StorageFileSource
from inkstave.config import get_settings
from inkstave.db.engine import create_engine_and_sessionmaker
from inkstave.redis_client import create_redis_pool
from inkstave.storage.factory import get_object_store

_settings = get_settings()
_PACKAGES_TOML = Path("infra/tectonic/packages.toml")


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    store = get_object_store(settings)
    packages = load_package_config(_PACKAGES_TOML, settings)
    runner = LocalTectonicRunner(
        bin_path=settings.tectonic_bin,
        cache_dir=Path(settings.tectonic_cache_dir),
        bundle_url=settings.tectonic_bundle_url or None,
        offline=settings.tectonic_offline,
        output_format=packages.format,
    )

    def make_service(session: Any) -> CompileService:
        return CompileService(
            settings=settings,
            runner=runner,
            docs=DbDocumentSource(session),
            files=StorageFileSource(session, store),
            packages=packages,
        )

    async def persist_outputs(
        session: Any, compile_id: UUID, project_id: UUID, result: CompileResult
    ) -> None:
        store_service = OutputStore(
            storage=store, repo=OutputRepository(session), settings=settings
        )
        await store_service.persist(compile_id, project_id, result)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = sessionmaker
    ctx["redis"] = await create_redis_pool(settings.redis_url)
    ctx["make_compile_service"] = make_service
    ctx["persist_hook"] = persist_outputs
    ctx["make_output_store"] = lambda session: OutputStore(
        storage=store, repo=OutputRepository(session), settings=settings
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    redis = ctx.get("redis")
    if redis is not None:
        await redis.aclose()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions = [
        func(run_compile, name="run_compile", max_tries=1, timeout=_settings.compile_job_timeout_s)
    ]
    # Hourly retention sweep (COMPILE_RETENTION_SWEEP_S defaults to 3600).
    cron_jobs = [cron(cleanup_compile_outputs, minute=0, run_at_startup=False)]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = _settings.compile_queue_name
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
