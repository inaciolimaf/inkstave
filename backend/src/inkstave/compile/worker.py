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

from inkstave.agent.api.jobs import agent_audit_cleanup, run_agent_turn
from inkstave.agent.settings import get_agent_settings
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
from inkstave.history.jobs import compact_history
from inkstave.mailer.jobs import send_email_job
from inkstave.mailer.sender import get_email_sender
from inkstave.notifications.jobs import sweep_notifications
from inkstave.redis_client import create_redis_pool
from inkstave.storage.factory import get_object_store

_settings = get_settings()
_PACKAGES_TOML = Path("infra/tectonic/packages.toml")


def _sweep_minutes(sweep_s: int) -> set[int]:
    """Convert a sub-hourly retention-sweep interval (seconds) into the set of
    ``minute`` values for an ARQ ``cron(...)`` so ``COMPILE_RETENTION_SWEEP_S``
    actually controls the cleanup schedule (spec 68 #84).

    For ``sweep_s >= 3600`` the job runs once per hour (``{0}``). Otherwise the
    interval is floored to whole minutes and the matching minutes are selected,
    e.g. 900s -> every 15 min ``{0, 15, 30, 45}``.
    """
    if sweep_s >= 3600:
        return {0}
    step = max(1, sweep_s // 60)
    return {m for m in range(60) if m % step == 0}


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    store = get_object_store(settings)
    packages = load_package_config(_PACKAGES_TOML, settings)
    runner: Any
    if settings.compile_mode == "mock":
        # e2e/test only (spec 54): no Tectonic subprocess — emit a canned PDF + log.
        from inkstave.testkit.compile_stub import MockTectonicRunner

        runner = MockTectonicRunner()
    else:
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
    ctx["object_store"] = store  # used by the history compaction job (spec 36)
    ctx["email_sender"] = get_email_sender(settings)  # used by the email job (spec 39)
    # The agent turn (run_agent_turn) needs AgentSettings, not the compile Settings
    # under ctx["settings"]; provide them so the worker can run agent jobs.
    ctx["agent_settings"] = get_agent_settings()
    if settings.llm_stub:
        # e2e/test only (spec 54): deterministic agent LLM, no network.
        from inkstave.testkit.llm_stub import StubAgentLLM

        ctx["llm_client"] = StubAgentLLM()


async def shutdown(ctx: dict[str, Any]) -> None:
    redis = ctx.get("redis")
    if redis is not None:
        await redis.aclose()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


class WorkerSettings:
    functions = [
        func(run_compile, name="run_compile", max_tries=1, timeout=_settings.compile_job_timeout_s),
        func(send_email_job, name="send_email_job", max_tries=3),
        func(compact_history, name="compact_history", max_tries=2),
        func(sweep_notifications, name="sweep_notifications", max_tries=2),
        func(run_agent_turn, name="run_agent_turn", max_tries=1),
        func(agent_audit_cleanup, name="agent_audit_cleanup", max_tries=1),
    ]
    cron_jobs = [
        # Retention sweep driven by COMPILE_RETENTION_SWEEP_S (default 3600 → hourly).
        cron(
            cleanup_compile_outputs,
            minute=_sweep_minutes(_settings.compile_retention_sweep_s),
            run_at_startup=False,
        ),
        # History compaction sweep (~every 5 min; HISTORY_COMPACT_INTERVAL_S documents intent).
        cron(compact_history, minute=set(range(0, 60, 5)), run_at_startup=False),
        # Notification expiry sweep (hourly; NOTIFICATION_SWEEP_INTERVAL_S documents intent).
        cron(sweep_notifications, minute=0, run_at_startup=False),
        # Optional agent-audit retention prune (spec 49/68 #207). The job is a no-op
        # unless AGENT_AUDIT_RETENTION_DAYS is positive, so the default deploy is inert.
        cron(agent_audit_cleanup, hour=3, minute=30, run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    queue_name = _settings.compile_queue_name
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
