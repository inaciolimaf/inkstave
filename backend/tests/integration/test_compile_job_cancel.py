"""Cancellation tests for the run_compile job (spec 22, spec 68 #93/#94).

Covers the pre-cancel short-circuit and the deterministic (event-driven)
cancel-during-run path. Shared fakes/helpers live in ``_compile_job_support.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.jobs import run_compile
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult
from inkstave.compile.stream import request_cancel
from inkstave.config import Settings
from tests.integration._compile_job_support import (
    CancelAwareWorkdirService,
    StubService,
    _ctx,
    _new_compile,
    _success,
)

pytestmark = pytest.mark.integration


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


async def test_cancel_during_run_trips_token(
    db_session: AsyncSession, redis: Any, tmp_path: Path
) -> None:
    # spec 68 #93/#94: real workdir + deterministic (event-driven) cancel, no sleeps.
    cid = await _new_compile(db_session)
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp_path))  # type: ignore[call-arg]
    service = CancelAwareWorkdirService(tmp_path)

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None: ...

    task = asyncio.create_task(
        run_compile(_ctx(db_session, redis, service, persist, settings), str(cid))
    )
    await service.running.wait()  # run() is in-flight at a known point
    await request_cancel(redis, cid, 300)  # the job's watcher will trip the token
    await task

    assert service.cancel_seen is True  # the token was tripped while running
    assert not (tmp_path / str(cid)).exists()  # cleanup backstop removed the workdir
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "cancelled"
