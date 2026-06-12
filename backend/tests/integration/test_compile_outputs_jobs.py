"""Integration tests for the compile job's output persistence (spec 23).

Shared helpers/constants live in ``_compile_outputs_support.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult
from inkstave.config import Settings
from inkstave.storage.local import LocalObjectStore
from tests.integration._compile_outputs_support import (
    _result,
    _seed,
    _SessionCtx,
    _StubService,
)

pytestmark = pytest.mark.integration


async def test_job_persists_outputs_and_cleans_workdir(
    db_session: AsyncSession, redis, tmp_path: Path
) -> None:
    from inkstave.compile.jobs import run_compile

    _, project, compile_row = await _seed(db_session)
    result = _result(tmp_path)
    result.workdir = tmp_path / "wd"  # the job cleans this up after persisting
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    async def persist(session: AsyncSession, cid, pid, res: CompileResult) -> None:
        await OutputStore(
            storage=backend, repo=OutputRepository(session), settings=settings
        ).persist(cid, pid, res)

    ctx = {
        "settings": settings,
        "redis": redis,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_compile_service": lambda _s: _StubService(result),
        "persist_hook": persist,
    }
    await run_compile(ctx, str(compile_row.id))

    row = await CompileRepository(db_session).get_by_id(compile_row.id)
    assert row is not None
    assert row.status == "success"
    assert row.has_pdf is True
    store = OutputStore(storage=backend, repo=OutputRepository(db_session), settings=settings)
    assert len(await store.list_outputs(compile_row.id)) == 4
    assert not (tmp_path / "wd").exists()  # workdir removed after persistence


async def test_job_persists_before_terminal_status_event(
    db_session: AsyncSession, redis, tmp_path: Path
) -> None:
    """AC2: outputs are persisted BEFORE the terminal status event is published.
    Spy on the persist hook and ``publish_status`` (instrumented on the job's
    collaborators, never editing jobs.py) and assert the recorded order."""
    import inkstave.compile.jobs as jobs_module
    from inkstave.compile.jobs import run_compile

    _, project, compile_row = await _seed(db_session)
    result = _result(tmp_path)
    result.workdir = tmp_path / "wd"
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    order: list[str] = []

    async def persist(session: AsyncSession, cid, pid, res: CompileResult) -> None:
        await OutputStore(
            storage=backend, repo=OutputRepository(session), settings=settings
        ).persist(cid, pid, res)
        order.append("persist")

    real_publish = jobs_module.publish_status

    async def spy_publish(*args, **kwargs):
        order.append("publish")
        return await real_publish(*args, **kwargs)

    ctx = {
        "settings": settings,
        "redis": redis,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_compile_service": lambda _s: _StubService(result),
        "persist_hook": persist,
    }
    monkey = pytest.MonkeyPatch()
    monkey.setattr(jobs_module, "publish_status", spy_publish)
    try:
        await run_compile(ctx, str(compile_row.id))
    finally:
        monkey.undo()

    # The RUNNING event publishes before persist; the terminal event publishes
    # last. The persist must precede that *terminal* publish.
    assert "persist" in order
    assert order[-1] == "publish"  # terminal status event is the final call
    last_publish = len(order) - 1
    assert order.index("persist") < last_publish
