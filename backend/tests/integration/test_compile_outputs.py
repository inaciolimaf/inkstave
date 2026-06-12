"""Integration tests for OutputStore persistence + deletion (spec 23).

Retention/eviction tests live in ``test_compile_outputs_retention.py`` and the
compile-job tests in ``test_compile_outputs_jobs.py``; shared helpers/constants
live in ``_compile_outputs_support.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.storage.local import LocalObjectStore
from tests.integration._compile_outputs_support import (
    FILES,
    _collect,
    _result,
    _seed,
    _store,
)

pytestmark = pytest.mark.integration


async def test_persist_records_rows_and_bytes(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))

    assert len(rows) == 4
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"pdf", "log", "synctex", "aux"}
    assert by_kind["pdf"].content_type == "application/pdf"
    assert by_kind["pdf"].size_bytes == len(FILES["output.pdf"][0])
    assert len(by_kind["pdf"].etag) == 64  # sha256 hex
    assert by_kind["pdf"].storage_key == f"compiles/{project.id}/{compile_row.id}/output.pdf"

    pdf = await store.open_pdf(compile_row.id)
    assert pdf is not None
    assert await _collect(pdf.read_range(0, pdf.size - 1)) == FILES["output.pdf"][0]
    assert await _collect(pdf.read_range(0, 4)) == FILES["output.pdf"][0][:5]


async def test_persist_is_idempotent(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    await store.persist(compile_row.id, project.id, _result(tmp_path))
    await store.persist(compile_row.id, project.id, _result(tmp_path))
    assert len(await store.list_outputs(compile_row.id)) == 4


async def test_delete_for_compile_removes_rows_and_objects(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    assert await backend.exists(rows[0].storage_key)

    await store.delete_for_compile(compile_row.id)
    assert await store.list_outputs(compile_row.id) == []
    assert await backend.exists(rows[0].storage_key) is False


async def test_delete_for_compile_is_idempotent(db_session: AsyncSession, tmp_path: Path) -> None:
    """Regression (spec 25): storage-first deletion is safe to re-run after a
    partial sweep — a second delete neither errors nor leaves rows behind."""
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    await store.persist(compile_row.id, project.id, _result(tmp_path))

    await store.delete_for_compile(compile_row.id)
    await store.delete_for_compile(compile_row.id)  # no-op, must not raise
    assert await store.list_outputs(compile_row.id) == []


async def test_delete_for_project_sweeps_storage(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))
    backend = LocalObjectStore(tmp_path / "blobs", 65536)

    await store.delete_for_project(project.id)
    assert await backend.exists(rows[0].storage_key) is False
