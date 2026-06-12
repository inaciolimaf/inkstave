"""Integration tests for OutputStore retention / eviction (spec 23/25).

Shared helpers/constants live in ``_compile_outputs_support.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.config import Settings
from inkstave.services.project import create_project
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory
from tests.integration._compile_outputs_support import (
    _compile_with_output,
    _result,
    _SessionCtx,
)

pytestmark = pytest.mark.integration


async def test_retention_selects_beyond_keep_window(
    db_session: AsyncSession,
) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    rows = [
        await _compile_with_output(db_session, project.id, user.id, now - timedelta(minutes=i))
        for i in range(4)  # i=0 newest ... i=3 oldest
    ]
    repo = OutputRepository(db_session)
    pruned = await repo.list_compiles_for_retention(
        keep_per_project=2, max_age_cutoff=now - timedelta(days=365), batch=10
    )
    # Keep the 2 newest; the 2 oldest are selected, oldest first.
    assert pruned == [rows[3].id, rows[2].id]


async def test_retention_batch_bound_binds(db_session: AsyncSession) -> None:
    """AC10: the batch is bounded. Seed N > batch eligible compiles and assert
    exactly ``batch`` ids come back — proving the SQL LIMIT is the binding
    constraint (the test would over-return if LIMIT were dropped)."""
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    # 5 compiles all eligible (keep_per_project=0 evicts every one of them).
    for i in range(5):
        await _compile_with_output(db_session, project.id, user.id, now - timedelta(minutes=i))
    repo = OutputRepository(db_session)
    pruned = await repo.list_compiles_for_retention(
        keep_per_project=0, max_age_cutoff=now - timedelta(days=365), batch=3
    )
    assert len(pruned) == 3  # LIMIT :batch binds even though 5 are eligible


async def test_cleanup_compile_outputs_job_evicts(db_session: AsyncSession, tmp_path: Path) -> None:
    """AC10 end-to-end: invoke ``cleanup_compile_outputs(ctx)`` itself (not just
    the repo helper) and assert evicted compiles lose both their storage objects
    and their ``compile_outputs`` rows, while retained compiles keep theirs."""
    from inkstave.compile.retention import cleanup_compile_outputs

    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    def make_store(session: AsyncSession) -> OutputStore:
        return OutputStore(storage=backend, repo=OutputRepository(session), settings=settings)

    # Two recent compiles to keep, two aged-out compiles to evict.
    keep = [
        await _compile_with_output(db_session, project.id, user.id, now - timedelta(minutes=i))
        for i in range(2)
    ]
    evict = [
        await _compile_with_output(db_session, project.id, user.id, now - timedelta(days=40 + i))
        for i in range(2)
    ]
    # Materialise the stored objects each row's storage_key points at.
    store = make_store(db_session)
    for row in keep + evict:
        await store.persist(row.id, project.id, _result(tmp_path))
    await db_session.flush()

    ctx = {
        "settings": settings,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_output_store": make_store,
    }
    summary = await cleanup_compile_outputs(ctx)
    assert summary["pruned"] == len(evict)

    repo = OutputRepository(db_session)
    for row in evict:
        assert await repo.list_for_compile(row.id) == []
        for key in await repo.storage_keys_for_compile(row.id):
            assert await backend.exists(key) is False
    for row in keep:
        rows = await repo.list_for_compile(row.id)
        assert rows
        assert await backend.exists(rows[0].storage_key)


async def test_retention_selects_by_age(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    old = await _compile_with_output(db_session, project.id, user.id, now - timedelta(days=40))
    await _compile_with_output(db_session, project.id, user.id, now)
    repo = OutputRepository(db_session)
    pruned = await repo.list_compiles_for_retention(
        keep_per_project=100, max_age_cutoff=now - timedelta(days=30), batch=10
    )
    assert pruned == [old.id]  # only the aged-out one, despite a generous keep window
