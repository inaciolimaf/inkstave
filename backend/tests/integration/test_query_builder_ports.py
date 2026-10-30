"""The statements moved from raw SQL to the builder keep their results; ``get_owned`` hides ids."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.db.ownership import get_owned
from inkstave.core.errors import NotFoundError
from inkstave.modules.agent.models import AgentSession
from inkstave.modules.compile.models.compile import Compile
from inkstave.modules.compile.models.compile_output import CompileOutput, OutputKind
from inkstave.modules.compile.outputs.repository import OutputRepository
from inkstave.modules.projects.catalog.service import create_project, get_project_name
from inkstave.modules.projects.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.modules.projects.tree import service as tree_service
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _project(session: AsyncSession):
    owner = await UserFactory.create(session)
    await session.flush()
    return owner, await create_project(session, owner.id, "P")


async def _compile(session: AsyncSession, project, owner, *, age_days: int, outputs: bool = True) -> Compile:
    row = Compile(
        project_id=project.id,
        requested_by=owner.id,
        status="success",
        main_file="main.tex",
        created_at=datetime.now(tz=UTC) - timedelta(days=age_days),
    )
    session.add(row)
    await session.flush()
    if outputs:
        session.add(
            CompileOutput(
                compile_id=row.id,
                project_id=project.id,
                name="main.pdf",
                rel_path="main.pdf",
                kind=OutputKind.PDF.value,
                storage_key=f"k/{row.id}",
                size_bytes=1,
                content_type="application/pdf",
                etag="e",
            )
        )
        await session.flush()
    return row


async def test_retention_picks_rows_past_the_window_or_the_cutoff(db_session: AsyncSession) -> None:
    owner, project = await _project(db_session)
    kept = await _compile(db_session, project, owner, age_days=1)
    beyond_window = await _compile(db_session, project, owner, age_days=2)
    too_old = await _compile(db_session, project, owner, age_days=40)
    await _compile(db_session, project, owner, age_days=50, outputs=False)  # nothing to prune

    ids = await OutputRepository(db_session).list_compiles_for_retention(
        keep_per_project=1, max_age_cutoff=datetime.now(tz=UTC) - timedelta(days=30), batch=10
    )

    assert ids == [too_old.id, beyond_window.id]
    assert kept.id not in ids


async def test_retention_respects_the_batch(db_session: AsyncSession) -> None:
    owner, project = await _project(db_session)
    oldest = await _compile(db_session, project, owner, age_days=9)
    await _compile(db_session, project, owner, age_days=8)

    ids = await OutputRepository(db_session).list_compiles_for_retention(
        keep_per_project=0, max_age_cutoff=datetime.now(tz=UTC), batch=1
    )

    assert ids == [oldest.id]


async def _folder(session: AsyncSession, project_id, name: str, parent_id) -> TreeEntity:
    return await tree_service.create_entity(session, project_id, TreeEntityType.folder, name, parent_id)


async def test_is_descendant_walks_the_subtree_only(db_session: AsyncSession) -> None:
    _owner, project = await _project(db_session)
    parent = await _folder(db_session, project.id, "a", None)
    child = await _folder(db_session, project.id, "b", parent.id)
    grandchild = await _folder(db_session, project.id, "c", child.id)
    sibling = await _folder(db_session, project.id, "d", None)

    assert await tree_service.is_descendant(db_session, project.id, parent.id, grandchild.id)
    assert await tree_service.is_descendant(db_session, project.id, parent.id, parent.id)
    assert not await tree_service.is_descendant(db_session, project.id, parent.id, sibling.id)
    assert not await tree_service.is_descendant(db_session, project.id, grandchild.id, parent.id)
    assert not await tree_service.is_descendant(db_session, uuid4(), parent.id, child.id)


async def test_get_project_name(db_session: AsyncSession) -> None:
    _owner, project = await _project(db_session)
    assert await get_project_name(db_session, project.id) == "P"
    assert await get_project_name(db_session, uuid4()) is None


async def test_get_owned_gives_the_same_error_for_missing_and_foreign(db_session: AsyncSession) -> None:
    owner, project = await _project(db_session)
    stranger = await UserFactory.create(db_session)
    row = AgentSession(project_id=project.id, user_id=owner.id, title="t", model="m")
    db_session.add(row)
    await db_session.flush()
    not_found = NotFoundError("Nothing here.")

    assert await get_owned(db_session, AgentSession, row.id, owner.id, not_found=not_found) is row
    for record_id, user_id, scope in (
        (row.id, stranger.id, {}),
        (uuid4(), owner.id, {}),
        (row.id, owner.id, {"project_id": uuid4()}),
    ):
        with pytest.raises(NotFoundError) as caught:
            await get_owned(db_session, AgentSession, record_id, user_id, not_found=not_found, **scope)
        assert caught.value is not_found
