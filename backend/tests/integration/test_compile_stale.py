"""Stuck compiles: enqueue after commit, stale rows, the reaper and the request lock.

A row left ``queued`` or ``running`` by a lost job must not hold a coalesced result or a
concurrency slot forever, and the reaper settles it. Shared helpers live in
``_compile_job_support.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import Settings
from inkstave.core.db.session import run_after_commit
from inkstave.modules.compile.models.compile import Compile
from inkstave.modules.compile.queue.coordinator import CompileCoordinator
from inkstave.modules.compile.queue.reaper import reap_stale_compiles
from inkstave.modules.compile.queue.repository import CompileRepository
from inkstave.modules.compile.queue.stale import stale_cutoffs
from inkstave.modules.projects.catalog.service import create_project
from tests.factories import UserFactory
from tests.integration._compile_job_support import _ctx

pytestmark = pytest.mark.integration

_LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)


class FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def enqueue(self, compile_id: UUID) -> str | None:
        self.calls.append(compile_id)
        return f"job-{compile_id}"


def _settings(**over: Any) -> Settings:
    return Settings(_env_file=None, **over)


async def _seed(db_session: AsyncSession) -> tuple[Any, Any]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    return user, project


async def _row(db_session: AsyncSession, user: Any, project: Any, status: str, **fields: Any) -> Compile:
    repo = CompileRepository(db_session)
    row = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    await repo.update(row, status=status, **fields)
    return row


async def test_stale_queued_row_is_not_coalesced(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    stuck = await _row(db_session, user, project, "queued", created_at=_LONG_AGO)
    coord = CompileCoordinator(
        settings=_settings(), repo=CompileRepository(db_session), enqueuer=FakeEnqueuer()
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=False
    )
    assert row.id != stuck.id
    assert row.status == "queued"


async def test_stale_running_row_is_not_coalesced(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    stuck = await _row(db_session, user, project, "running", started_at=_LONG_AGO)
    coord = CompileCoordinator(
        settings=_settings(), repo=CompileRepository(db_session), enqueuer=FakeEnqueuer()
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=False
    )
    assert row.id != stuck.id


async def test_stale_rows_do_not_hold_the_concurrency_caps(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    await _row(db_session, user, project, "running", started_at=_LONG_AGO)
    coord = CompileCoordinator(
        settings=_settings(compile_max_concurrent_per_project=1, compile_max_concurrent_per_user=1),
        repo=CompileRepository(db_session),
        enqueuer=FakeEnqueuer(),
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=True
    )
    assert row.status == "queued"


async def test_enqueue_waits_for_the_commit(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    enq = FakeEnqueuer()
    coord = CompileCoordinator(settings=_settings(), repo=CompileRepository(db_session), enqueuer=enq)
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=False
    )
    assert enq.calls == []  # nothing is on the queue before the row is committed
    await run_after_commit(db_session)
    assert enq.calls == [row.id]
    assert row.job_id == str(row.id)


async def test_request_takes_a_transaction_lock_before_counting(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    coord = CompileCoordinator(
        settings=_settings(), repo=CompileRepository(db_session), enqueuer=FakeEnqueuer()
    )
    await coord.request_compile(project_id=project.id, user_id=user.id, main_file="main.tex", force=False)
    held = await db_session.scalar(
        text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND pid = pg_backend_pid()"
        )
    )
    assert held is not None and held >= 2  # the project lock and the user lock


async def test_reaper_settles_stale_rows_and_keeps_fresh_ones(db_session: AsyncSession, redis: Any) -> None:
    user, project = await _seed(db_session)
    stale_queued = await _row(db_session, user, project, "queued", created_at=_LONG_AGO)
    stale_running = await _row(db_session, user, project, "running", started_at=_LONG_AGO)
    fresh = await _row(db_session, user, project, "running", started_at=datetime.now(UTC))
    done = await _row(db_session, user, project, "success", created_at=_LONG_AGO)
    await db_session.flush()

    summary = await reap_stale_compiles(_ctx(db_session, redis, None, None, _settings()))

    assert summary == {"reaped": 2}
    for row in (stale_queued, stale_running, fresh, done):
        await db_session.refresh(row)
    assert stale_queued.status == "timeout" and stale_queued.finished_at is not None
    assert stale_running.status == "timeout"
    assert "stale" in (stale_running.error_message or "")
    assert fresh.status == "running"
    assert done.status == "success"


async def test_reaped_project_has_no_active_compile(db_session: AsyncSession, redis: Any) -> None:
    user, project = await _seed(db_session)
    await _row(db_session, user, project, "queued", created_at=_LONG_AGO)
    await reap_stale_compiles(_ctx(db_session, redis, None, None, _settings()))
    cutoffs = stale_cutoffs(_settings(), datetime.now(UTC))
    assert await CompileRepository(db_session).find_active_for_project(project.id, cutoffs) is None
