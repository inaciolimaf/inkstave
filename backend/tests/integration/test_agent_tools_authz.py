"""Integration tests for agent propose_edit + authorization (spec 42).

Shared helpers/fixtures live in ``_agent_tools_support.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.tools.list_tree import ListTreeArgs, ListTreeTool
from inkstave.agent.tools.locate_section import LocateSectionArgs, LocateSectionTool
from inkstave.agent.tools.propose_edit import ProposeEditArgs, ProposeEditTool
from inkstave.agent.tools.read_file import ReadFileArgs, ReadFileTool
from inkstave.agent.tools.search_project import SearchProjectArgs, SearchProjectTool
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import get_document, set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.factories import UserFactory

from ._agent_tools_support import _ctx, seed

pytestmark = pytest.mark.integration

__all__ = ["seed"]


async def test_propose_edit_stages_without_changing_doc(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    before = (await get_document(db_session, seed.project_id, seed.main_id)).content
    version = (await get_document(db_session, seed.project_id, seed.main_id)).version

    result = await ProposeEditTool().run(
        ProposeEditArgs(
            doc_id=str(seed.main_id), mode="range", new_text="rewritten", start_line=3, end_line=4
        ),
        ctx,
    )
    assert result.ok and result.data is not None
    assert result.data["staged"] is True and result.data["base_version"] == str(version)  # AC5
    assert len(ctx.staged_edits) == 1 and ctx.staged_edits[0].new_text == "rewritten"
    # The document content is unchanged in the DB.
    after = (await get_document(db_session, seed.project_id, seed.main_id)).content
    assert after == before


async def test_viewer_cannot_propose_but_can_read(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.viewer.id)
    denied = await ProposeEditTool().run(
        ProposeEditArgs(doc_id=str(seed.main_id), mode="full", new_text="x"), ctx
    )
    assert not denied.ok and denied.error is not None and denied.error.code == "forbidden"  # AC6
    # AC6: every read tool still succeeds for a viewer (not an authorization error).
    readable = await ReadFileTool().run(ReadFileArgs(doc_id=str(seed.main_id)), ctx)
    assert readable.ok  # read tools still work for a viewer
    searched = await SearchProjectTool().run(SearchProjectArgs(query="introduction"), ctx)
    assert searched.ok
    listed = await ListTreeTool().run(ListTreeArgs(depth=2), ctx)
    assert listed.ok
    located = await LocateSectionTool().run(LocateSectionArgs(name="introduction"), ctx)
    assert located.ok


async def test_cross_project_doc_is_not_found(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    other_owner = await UserFactory.create(db_session)
    other = await create_project(db_session, other_owner.id, "Other")
    other_doc = await create_entity(db_session, other.id, TreeEntityType.doc, "secret.tex", None)
    await set_content_from_collab(db_session, other_doc.id, "TOP SECRET")
    await db_session.commit()

    ctx = _ctx(db_session, seed.project_id, seed.owner.id)  # scoped to the first project
    read = await ReadFileTool().run(ReadFileArgs(doc_id=str(other_doc.id)), ctx)
    assert not read.ok and read.error is not None and read.error.code == "not_found"  # AC7
    edit = await ProposeEditTool().run(
        ProposeEditArgs(doc_id=str(other_doc.id), mode="full", new_text="x"), ctx
    )
    assert not edit.ok and edit.error is not None and edit.error.code == "not_found"


async def test_propose_edit_range_out_of_bounds(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    result = await ProposeEditTool().run(
        ProposeEditArgs(
            doc_id=str(seed.main_id), mode="range", new_text="x", start_line=0, end_line=9999
        ),
        ctx,
    )
    assert not result.ok and result.error is not None
    assert result.error.code == "invalid_args"  # AC10
