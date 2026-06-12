"""Shared fakes/helpers for the run_compile job integration tests (spec 22).

Module-level support used by the ``test_compile_job*.py`` siblings. Not
``test_``-prefixed so pytest does not collect it as a test module.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.limits import CancelToken
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileArtifact, CompileResult, CompileStatus
from inkstave.config import Settings
from inkstave.observability.context import current_context
from inkstave.services.project import create_project
from tests.factories import UserFactory


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


class CancelAwareWorkdirService:
    """Cancel-path fake that (a) creates a *real* workdir so the job's cleanup
    backstop is exercised (spec 68 #93) and (b) is driven deterministically by
    ``asyncio.Event``\\ s instead of a real sleep/poll loop (spec 68 #94).

    ``running`` is set once ``compile`` is in-flight (so the test cancels at a known
    point); the service then awaits the cancel token (``cancel.wait()``), which the
    job's watcher trips once the test requests cancellation — no sleep/poll loop.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self.cancel_seen = False
        self.running = asyncio.Event()
        self.workdir: Path | None = None

    async def compile(self, opts: Any, cancel: CancelToken) -> CompileResult:
        workdir = self._root / str(opts.compile_id)
        (workdir / "output").mkdir(parents=True, exist_ok=True)
        self.workdir = workdir
        self.running.set()  # signal the test that run() is in-flight
        await cancel.wait()  # block until the job's watcher trips the token
        self.cancel_seen = cancel.is_cancelled
        return CompileResult(
            status=CompileStatus.CANCELLED,
            pdf=None,
            log_text="",
            stdout="",
            stderr="",
            exit_code=None,
            duration_ms=1,
            workdir=workdir,  # so the job's cleanup backstop is exercised (spec 68 #93)
        )


def _ctx(
    db_session: AsyncSession,
    redis: Any,
    service: Any,
    persist: Any,
    settings: Settings | None = None,
) -> dict[str, Any]:
    return {
        "settings": settings or Settings(_env_file=None),  # type: ignore[call-arg]
        "redis": redis,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_compile_service": lambda _session: service,
        "persist_hook": persist,
    }


class WorkdirCreatingService:
    """Creates the real workdir (as the live service does under keep_workdir=True),
    then returns a result or raises — to exercise the job's cleanup backstop."""

    def __init__(
        self, root: Path, *, result: CompileResult | None = None, raises: Exception | None = None
    ) -> None:
        self._root = root
        self._result = result
        self._raises = raises

    async def compile(self, opts: Any, cancel: CancelToken) -> CompileResult:
        workdir = self._root / str(opts.compile_id)
        (workdir / "output").mkdir(parents=True, exist_ok=True)
        if self._raises is not None:
            raise self._raises
        assert self._result is not None
        self._result.workdir = workdir
        return self._result


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


class ContextCapturingService:
    """Records the observability context bound while the compile job runs (spec 51)."""

    def __init__(self, result: CompileResult) -> None:
        self._result = result
        self.context: dict[str, str] = {}

    async def compile(self, opts: Any, cancel: CancelToken) -> CompileResult:
        self.context = current_context()
        return self._result
