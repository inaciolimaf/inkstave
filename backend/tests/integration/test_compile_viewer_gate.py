"""COMPILE_ALLOWED_FOR_VIEWERS is enforced by the job and the SSE route, as by the trigger route."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import Settings, get_settings
from inkstave.core.deps import get_settings_dep
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.compile.queue.jobs import run_compile
from inkstave.modules.compile.queue.repository import CompileRepository
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from tests.factories import UserFactory
from tests.integration._compile_job_support import StubService, _ctx, _success

pytestmark = pytest.mark.integration


def _settings(*, viewers_compile: bool) -> Settings:
    return Settings(_env_file=None, compile_allowed_for_viewers=viewers_compile)


async def _project_with_viewer(db_session: AsyncSession) -> tuple[Any, Any, Any]:
    owner = await UserFactory.create(db_session)
    viewer = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, owner.id, "P")
    db_session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=viewer.id,
            role=MembershipRole.viewer,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()
    return owner, viewer, project


async def _compile_by(db_session: AsyncSession, project: Any, user: Any, status: str) -> UUID:
    repo = CompileRepository(db_session)
    row = await repo.create(project_id=project.id, requested_by=user.id, main_file="main.tex")
    await repo.update(row, status=status)
    return row.id


async def test_job_refuses_a_viewer_when_viewers_cannot_compile(db_session: AsyncSession, redis: Any) -> None:
    _owner, viewer, project = await _project_with_viewer(db_session)
    cid = await _compile_by(db_session, project, viewer, "queued")
    service = StubService(_success())

    async def persist(*_args: Any) -> None: ...

    ctx = _ctx(db_session, redis, service, persist, _settings(viewers_compile=False))
    await run_compile(ctx, str(cid))

    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None
    assert row.status == "error"
    assert "no longer authorized" in (row.error_message or "")


async def test_job_runs_for_a_viewer_when_viewers_can_compile(db_session: AsyncSession, redis: Any) -> None:
    _owner, viewer, project = await _project_with_viewer(db_session)
    cid = await _compile_by(db_session, project, viewer, "queued")

    async def persist(*_args: Any) -> None: ...

    ctx = _ctx(db_session, redis, StubService(_success()), persist, _settings(viewers_compile=True))
    await run_compile(ctx, str(cid))

    row = await CompileRepository(db_session).get_by_id(cid)
    assert row is not None and row.status == "success"


async def test_sse_refuses_a_viewer_when_viewers_cannot_compile(
    async_client: AsyncClient, app: Any, db_session: AsyncSession
) -> None:
    _owner, viewer, project = await _project_with_viewer(db_session)
    cid = await _compile_by(db_session, project, viewer, "success")  # terminal: the stream closes at once
    app.dependency_overrides[get_settings_dep] = lambda: _settings(viewers_compile=False)
    token, _ = build_token_service(get_settings()).create_access_token(viewer)

    resp = await async_client.get(
        f"/api/v1/projects/{project.id}/compile/{cid}/events", headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 403
    assert resp.json()["error"]["type"] == "insufficient_role"
