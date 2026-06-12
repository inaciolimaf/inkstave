"""Unit tests for CompileCoordinator debounce/concurrency/enqueue (spec 22)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.coordinator import CompileConcurrencyError, CompileCoordinator
from inkstave.compile.repository import CompileRepository
from inkstave.config import Settings
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
