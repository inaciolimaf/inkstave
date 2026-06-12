"""Workdir-cleanup regression tests for the run_compile job (spec 22/25).

A service exception or a persistence failure must never orphan the compile
workdir. Shared fakes/helpers live in ``_compile_job_support.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.jobs import run_compile
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileResult
from inkstave.config import Settings
from tests.integration._compile_job_support import (
    WorkdirCreatingService,
    _ctx,
    _new_compile,
    _success,
)

pytestmark = pytest.mark.integration


async def test_workdir_removed_when_service_raises(
    db_session: AsyncSession, redis: Any, tmp_path: Path
) -> None:
    """Regression (spec 25): a service exception must not orphan the workdir."""
    cid = await _new_compile(db_session)
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp_path))  # type: ignore[call-arg]
    service = WorkdirCreatingService(tmp_path, raises=RuntimeError("kaboom"))

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None: ...

    await run_compile(_ctx(db_session, redis, service, persist, settings), str(cid))

    assert not (tmp_path / str(cid)).exists()
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "error"


async def test_workdir_removed_on_persistence_failure(
    db_session: AsyncSession, redis: Any, tmp_path: Path
) -> None:
    """Regression (spec 25): a persistence failure must not orphan the workdir."""
    cid = await _new_compile(db_session)
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp_path))  # type: ignore[call-arg]
    service = WorkdirCreatingService(tmp_path, result=_success())

    async def persist(s: Any, c: UUID, p: UUID, r: CompileResult) -> None:
        raise RuntimeError("storage down")

    await run_compile(_ctx(db_session, redis, service, persist, settings), str(cid))

    assert not (tmp_path / str(cid)).exists()
    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "error"
    assert "output persistence failed" in (row.error_message or "")
