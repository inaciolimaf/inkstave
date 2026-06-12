"""Spec 63: the demo seed produces an idempotent, multi-file LaTeX project."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import build_password_hasher
from inkstave.bootstrap.seed import DEMO_EMAIL, seed_demo
from inkstave.config import get_settings
from inkstave.db.models.document import Document
from inkstave.db.models.project import Project
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.db.models.user import User
from inkstave.services.document_service import read_content_for_collab
from inkstave.services.user import normalise_email

pytestmark = pytest.mark.integration


def _hasher() -> Any:
    return build_password_hasher(get_settings())


async def _count(session: AsyncSession, model: Any) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def _counts(session: AsyncSession) -> dict[str, int]:
    return {
        "users": await _count(session, User),
        "projects": await _count(session, Project),
        "entities": await _count(session, TreeEntity),
        "documents": await _count(session, Document),
    }


async def test_seed_creates_multifile_project(db_session: AsyncSession) -> None:  # AC1
    created = await seed_demo(db_session, _hasher(), settings=get_settings())
    assert created is True

    user = await db_session.scalar(
        select(User).where(User.email == normalise_email(DEMO_EMAIL))
    )
    assert user is not None
    project = await db_session.scalar(select(Project).where(Project.owner_id == user.id))
    assert project is not None

    docs = (
        await db_session.scalars(
            select(TreeEntity).where(
                TreeEntity.project_id == project.id, TreeEntity.type == TreeEntityType.doc
            )
        )
    ).all()
    names = {d.name for d in docs}
    assert "main.tex" in names
    assert len(docs) >= 2  # multi-file: main.tex plus at least one more doc

    # Every seeded doc has non-empty content.
    for doc in docs:
        content = await read_content_for_collab(db_session, doc.id)
        assert content.strip(), f"{doc.name} has empty content"


async def test_seed_is_idempotent_with_stable_counts(db_session: AsyncSession) -> None:  # AC2
    assert await seed_demo(db_session, _hasher(), settings=get_settings()) is True
    before = await _counts(db_session)
    assert await seed_demo(db_session, _hasher(), settings=get_settings()) is False
    after = await _counts(db_session)
    assert before == after


async def test_main_references_included_file(db_session: AsyncSession) -> None:  # AC3
    await seed_demo(db_session, _hasher(), settings=get_settings())
    user = await db_session.scalar(
        select(User).where(User.email == normalise_email(DEMO_EMAIL))
    )
    assert user is not None
    project = await db_session.scalar(select(Project).where(Project.owner_id == user.id))
    assert project is not None
    main = await db_session.scalar(
        select(TreeEntity).where(
            TreeEntity.project_id == project.id, TreeEntity.name == "main.tex"
        )
    )
    assert main is not None
    content = await read_content_for_collab(db_session, main.id)
    assert r"\input{sections/intro}" in content


async def test_seed_force_does_not_duplicate(db_session: AsyncSession) -> None:  # AC2 (force)
    assert await seed_demo(db_session, _hasher(), settings=get_settings()) is True
    before = await _counts(db_session)
    # force in a non-prod env must not create duplicate rows for the same demo email.
    assert await seed_demo(db_session, _hasher(), settings=get_settings(), force=True) is False
    assert await _counts(db_session) == before
