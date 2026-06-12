"""Integration tests for the project service layer (real test DB)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.user import User
from inkstave.services.project import (
    ProjectNotFoundError,
    create_project,
    get_owned_project,
    list_projects,
    rename_project,
    soft_delete_project,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _user(db_session: AsyncSession) -> User:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    return user


async def test_create_sets_owner_and_defaults(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    project = await create_project(db_session, user.id, "My Paper")
    assert project.owner_id == user.id
    assert project.name == "My Paper"
    assert project.root_doc_id is None
    assert project.deleted_at is None


async def test_get_owned_project_raises_for_missing(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    with pytest.raises(ProjectNotFoundError):
        await get_owned_project(db_session, user.id, uuid4())


async def test_get_owned_project_raises_for_other_owner(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    other = await _user(db_session)
    project = await create_project(db_session, owner.id, "Owned")
    with pytest.raises(ProjectNotFoundError):
        await get_owned_project(db_session, other.id, project.id)


async def test_soft_delete_hides_project(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    project = await create_project(db_session, user.id, "Doomed")
    await soft_delete_project(db_session, user.id, project.id)
    await db_session.refresh(project)
    assert project.deleted_at is not None
    with pytest.raises(ProjectNotFoundError):
        await get_owned_project(db_session, user.id, project.id)


async def test_list_excludes_deleted_and_orders_by_recency(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    first = await create_project(db_session, user.id, "First")
    await create_project(db_session, user.id, "Second")
    # Bump `first` so it becomes the most recently updated.
    await rename_project(db_session, user.id, first.id, "First renamed")

    items, total = await list_projects(db_session, user.id, limit=50, offset=0)
    assert total == 2
    assert items[0].id == first.id  # newest updated_at first

    await soft_delete_project(db_session, user.id, first.id)
    items, total = await list_projects(db_session, user.id, limit=50, offset=0)
    assert total == 1
    assert all(p.id != first.id for p in items)


async def test_rename_bumps_updated_at(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    project = await create_project(db_session, user.id, "Before")
    before = project.updated_at
    renamed = await rename_project(db_session, user.id, project.id, "After")
    assert renamed.name == "After"
    assert renamed.updated_at > before
