"""Unit tests for CompileCoordinator debounce/concurrency/enqueue (spec 22).

Classification note (issue 81): although these tests live under ``tests/unit/``
and the coordinator's debounce/coalesce logic itself is HTTP-free, the
coordinator's concurrency caps and coalescing are expressed *entirely* through
``CompileRepository`` queries (active counts, in-flight lookup) against real
rows. ``CompileRepository`` is intrinsic to the coordinator — faking it would
just re-implement the SQL we are trying to exercise — so these tests use the
real ``db_session`` and carry ``pytest.mark.integration`` deliberately. The
dedicated ``CompileRepository`` tests below (issue 79) share the same rationale.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.coordinator import CompileConcurrencyError, CompileCoordinator
from inkstave.compile.repository import CompileRepository
from inkstave.config import Settings
from inkstave.db.models.compile import CompileJobStatus
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def enqueue(self, compile_id: UUID) -> str | None:
        self.calls.append(compile_id)
        return f"job-{compile_id}"


def _settings(**over: object) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def test_job_timeout_must_exceed_engine_timeout() -> None:
    from pydantic import ValidationError

    # Valid: job timeout strictly greater than the engine timeout.
    _settings(tectonic_compile_timeout_s=60, compile_job_timeout_s=120)
    with pytest.raises(ValidationError):
        _settings(tectonic_compile_timeout_s=120, compile_job_timeout_s=120)


async def _seed(db_session: AsyncSession):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    return user, project


async def test_creates_and_enqueues(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    enq = FakeEnqueuer()
    coord = CompileCoordinator(
        settings=_settings(), repo=CompileRepository(db_session), enqueuer=enq
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=False
    )
    assert row.status == "queued"
    assert row.job_id == f"job-{row.id}"
    assert enq.calls == [row.id]


async def test_coalesce_returns_inflight(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    existing = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    enq = FakeEnqueuer()
    coord = CompileCoordinator(
        settings=_settings(compile_debounce_coalesce=True), repo=repo, enqueuer=enq
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=False
    )
    assert row.id == existing.id
    assert enq.calls == []  # no new job enqueued


async def test_force_creates_new_when_under_cap(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    existing = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    enq = FakeEnqueuer()
    coord = CompileCoordinator(
        settings=_settings(compile_max_concurrent_per_project=5), repo=repo, enqueuer=enq
    )
    row = await coord.request_compile(
        project_id=project.id, user_id=user.id, main_file="main.tex", force=True
    )
    assert row.id != existing.id
    assert enq.calls == [row.id]


async def test_project_concurrency_cap_raises(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    coord = CompileCoordinator(
        settings=_settings(compile_max_concurrent_per_project=1),
        repo=repo,
        enqueuer=FakeEnqueuer(),
    )
    with pytest.raises(CompileConcurrencyError):
        await coord.request_compile(
            project_id=project.id, user_id=user.id, main_file="main.tex", force=True
        )


async def test_user_concurrency_cap_raises(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    other = await create_project(db_session, user.id, "Other")
    repo = CompileRepository(db_session)
    await repo.create(project_id=other.id, requested_by=user.id, main_file="main.tex")
    coord = CompileCoordinator(
        settings=_settings(
            compile_max_concurrent_per_project=10, compile_max_concurrent_per_user=1
        ),
        repo=repo,
        enqueuer=FakeEnqueuer(),
    )
    with pytest.raises(CompileConcurrencyError):
        await coord.request_compile(
            project_id=project.id, user_id=user.id, main_file="main.tex", force=True
        )


# --- CompileRepository unit tests (issue 79 / spec 22 §8) ------------------- #
#
# CRUD, active counts and latest lookups exercised directly against the test DB,
# in isolation from the coordinator.


async def test_repo_create_and_get(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    row = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    assert row.id is not None
    assert row.status == CompileJobStatus.QUEUED.value
    # get is scoped by (project_id, compile_id).
    got = await repo.get(project.id, row.id)
    assert got is not None and got.id == row.id
    # wrong project scope returns nothing.
    other = await create_project(db_session, user.id, "Other")
    assert await repo.get(other.id, row.id) is None


async def test_repo_get_latest_returns_most_recent(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    first = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    second = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    # ``created_at`` defaults to ``func.now()`` (transaction start time), so rows
    # created in the same test transaction share an identical timestamp and the
    # ``id``-based tiebreaker — a random UUID — would decide ordering. Stamp a
    # strictly-later ``created_at`` on the second row so "most recent" is
    # well-defined (in production successive compiles land in separate
    # transactions seconds apart).
    first.created_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    second.created_at = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)
    await db_session.flush()
    latest = await repo.get_latest(project.id)
    assert latest is not None
    assert latest.id == second.id


async def test_repo_get_latest_successful(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    queued = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    ok = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    await repo.update(ok, status=CompileJobStatus.SUCCESS.value)
    latest_ok = await repo.get_latest_successful(project.id)
    assert latest_ok is not None
    assert latest_ok.id == ok.id
    assert latest_ok.id != queued.id


async def test_repo_find_active_for_project(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    repo = CompileRepository(db_session)
    active = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    found = await repo.find_active_for_project(project.id)
    assert found is not None and found.id == active.id
    # once terminal, it is no longer active.
    await repo.update(active, status=CompileJobStatus.SUCCESS.value)
    assert await repo.find_active_for_project(project.id) is None


async def test_repo_count_active_for_project_scope(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    other = await create_project(db_session, user.id, "Other")
    repo = CompileRepository(db_session)
    a = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    await repo.create(project_id=other.id, requested_by=user.id, main_file="main.tex")
    assert await repo.count_active_for_project(project.id) == 2
    assert await repo.count_active_for_project(other.id) == 1
    # terminal rows drop out of the active count.
    await repo.update(a, status=CompileJobStatus.SUCCESS.value)
    assert await repo.count_active_for_project(project.id) == 1


async def test_repo_count_active_for_user_scope(db_session: AsyncSession) -> None:
    user, project = await _seed(db_session)
    other_project = await create_project(db_session, user.id, "Other")
    repo = CompileRepository(db_session)
    await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    one = await repo.create(project_id=other_project.id, requested_by=user.id, main_file="main.tex")
    assert await repo.count_active_for_user(user.id) == 2
    await repo.update(one, status=CompileJobStatus.SUCCESS.value)
    assert await repo.count_active_for_user(user.id) == 1
