"""Integration tests for the run_compile ARQ job with a stubbed service (spec 22).

Core run-result tests (metrics/context, success/manifest, failure, error) plus
the no-auto-retry registration check. Workdir-cleanup and cancellation tests live
in the ``test_compile_job_workdir.py`` / ``test_compile_job_cancel.py`` siblings;
shared fakes/helpers live in ``_compile_job_support.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.jobs import run_compile
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult, CompileStatus
from tests.integration._compile_job_support import (
    ContextCapturingService,
    StubService,
    _ctx,
    _new_compile,
    _success,
)

pytestmark = pytest.mark.integration


async def test_compile_job_records_metrics_and_binds_context(
    db_session: AsyncSession, redis: Any
) -> None:
    from prometheus_client import REGISTRY

    cid = await _new_compile(db_session)

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None:
        pass

    def count() -> float:
        return REGISTRY.get_sample_value("inkstave_compile_total", {"status": "success"}) or 0.0

    before = count()
    service = ContextCapturingService(_success())
    await run_compile(_ctx(db_session, redis, service, persist), str(cid), request_id="req-trace-1")

    assert count() == before + 1  # AC7: inkstave_compile_total{status="success"}
    assert (
        REGISTRY.get_sample_value(
            "inkstave_compile_duration_seconds_count", {"engine": "tectonic", "status": "success"}
        )
        is not None
    )
    # The job's context carries job_name + the chained request_id of the enqueuer.
    assert service.context["job_name"] == "run_compile"
    assert service.context["request_id"] == "req-trace-1"
    assert "job_id" in service.context


async def test_success_updates_row_and_manifest(db_session: AsyncSession, redis: Any) -> None:
    cid = await _new_compile(db_session)
    persisted: list[tuple[UUID, CompileResult]] = []

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None:
        persisted.append((c, r))

    await run_compile(_ctx(db_session, redis, StubService(_success()), persist), str(cid))

    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "success"
    assert row.has_pdf is True
    assert row.duration_ms == 42
    assert row.artifact_manifest and row.artifact_manifest[0]["content_type"] == "application/pdf"
    assert len(persisted) == 1


async def test_failure_records_log_excerpt(db_session: AsyncSession, redis: Any) -> None:
    cid = await _new_compile(db_session)
    result = CompileResult(
        status=CompileStatus.FAILURE,
        pdf=None,
        log_text="! Undefined control sequence",
        stdout="",
        stderr="",
        exit_code=1,
        duration_ms=5,
    )

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None: ...

    await run_compile(_ctx(db_session, redis, StubService(result), persist), str(cid))
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "failure"
    assert row.has_pdf is False
    assert "Undefined control sequence" in (row.log_excerpt or "")


async def test_unexpected_exception_is_error_status(db_session: AsyncSession, redis: Any) -> None:
    cid = await _new_compile(db_session)

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None: ...

    await run_compile(
        _ctx(db_session, redis, StubService(raises=RuntimeError("boom")), persist), str(cid)
    )
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "error"
    assert "boom" in (row.error_message or "")


def test_run_compile_job_does_not_auto_retry() -> None:
    # AC4 / spec 68 #80: the registered run_compile job must not auto-retry on a
    # transient error — max_tries == 1.
    from inkstave.compile.worker import WorkerSettings

    run_compile_func = next(
        f for f in WorkerSettings.functions if getattr(f, "name", None) == "run_compile"
    )
    assert run_compile_func.max_tries == 1
