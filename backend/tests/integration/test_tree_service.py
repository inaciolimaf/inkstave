"""Integration tests for tree-service internals (real test DB)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.project import create_project
from inkstave.services.tree_service import (
    create_entity,
    ensure_root,
    is_descendant,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_ensure_root_is_idempotent(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")  # creates a root
    root1 = await ensure_root(db_session, project.id)
    root2 = await ensure_root(db_session, project.id)
    assert root1.id == root2.id
    assert root1.is_root is True


async def test_is_descendant_detects_subtree(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    root = await ensure_root(db_session, project.id)

    a = await create_entity(db_session, project.id, TreeEntityType.folder, "A", root.id)
    b = await create_entity(db_session, project.id, TreeEntityType.folder, "B", a.id)
    c = await create_entity(db_session, project.id, TreeEntityType.doc, "c.tex", b.id)
    sibling = await create_entity(db_session, project.id, TreeEntityType.folder, "Other", root.id)

    assert await is_descendant(db_session, project.id, a.id, a.id) is True  # self
    assert await is_descendant(db_session, project.id, a.id, b.id) is True
    assert await is_descendant(db_session, project.id, a.id, c.id) is True
    assert await is_descendant(db_session, project.id, a.id, sibling.id) is False
