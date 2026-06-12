"""Integration tests for the run_compile ARQ job with a stubbed service (spec 22)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.jobs import run_compile
from inkstave.compile.limits import CancelToken
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileArtifact, CompileResult, CompileStatus
from inkstave.compile.stream import request_cancel
from inkstave.config import Settings
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class StubService:
    def __init__(
        self, result: CompileResult | None = None, *, raises: Exception | None = None
    ) -> None:
        self._result = result
        self._raises = raises
        self.cancel_seen = False

    async def compile(self, opts: Any, cancel: CancelToken) -> CompileResult:
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        return self._result


class CancelAwareService:
    def __init__(self) -> None:
        self.cancel_seen = False

    async def compile(self, opts: Any, cancel: CancelToken) -> CompileResult:
        for _ in range(200):
            if cancel.is_cancelled:
                self.cancel_seen = True
                return CompileResult(
                    status=CompileStatus.CANCELLED,
                    pdf=None,
                    log_text="",
                    stdout="",
                    stderr="",
                    exit_code=None,
                    duration_ms=1,
                )
            await asyncio.sleep(0.01)
        return CompileResult(
            status=CompileStatus.SUCCESS,
            pdf=None,
            log_text="",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=1,
        )


def _ctx(db_session: AsyncSession, redis: Any, service: Any, persist: Any) -> dict[str, Any]:
    return {
        "settings": Settings(_env_file=None),  # type: ignore[call-arg]
        "redis": redis,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_compile_service": lambda _session: service,
        "persist_hook": persist,
    }


async def _new_compile(db_session: AsyncSession) -> UUID:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    row = await CompileRepository(db_session).create(
        project_id=project.id, requested_by=user.id, main_file="main.tex"
    )
    return row.id


def _success() -> CompileResult:
    return CompileResult(
        status=CompileStatus.SUCCESS,
        pdf=CompileArtifact(
            "output.pdf", "output.pdf", __import__("pathlib").Path("/x"), 10, "application/pdf"
        ),
        log_text="the log",
        stdout="",
        stderr="",
        exit_code=0,
        duration_ms=42,
        artifacts=[
            CompileArtifact(
                "output.pdf", "output.pdf", __import__("pathlib").Path("/x"), 10, "application/pdf"
            )
        ],
    )


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


async def test_precancelled_exits_without_compiling(db_session: AsyncSession, redis: Any) -> None:
    cid = await _new_compile(db_session)
    await request_cancel(redis, cid, 300)
    service = StubService(_success())

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None:
        raise AssertionError("persist must not run for a cancelled compile")

    await run_compile(_ctx(db_session, redis, service, persist), str(cid))
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "cancelled"


async def test_cancel_during_run_trips_token(db_session: AsyncSession, redis: Any) -> None:
    cid = await _new_compile(db_session)
    service = CancelAwareService()

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None: ...

    task = asyncio.create_task(run_compile(_ctx(db_session, redis, service, persist), str(cid)))
    await asyncio.sleep(0.05)
    await request_cancel(redis, cid, 300)
    await task

    assert service.cancel_seen is True
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "cancelled"
