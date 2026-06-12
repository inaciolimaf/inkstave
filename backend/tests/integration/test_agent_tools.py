"""Integration tests for agent read tools against seeded 12/13 services (spec 42).

Shared helpers/fixtures live in ``_agent_tools_support.py``; authorization and
act-node graph tests live in ``test_agent_tools_authz.py`` and
``test_agent_tools_graph.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.tools.list_tree import ListTreeArgs, ListTreeTool
from inkstave.agent.tools.locate_section import LocateSectionArgs, LocateSectionTool
from inkstave.agent.tools.read_file import ReadFileArgs, ReadFileTool
from inkstave.agent.tools.search_project import SearchProjectArgs, SearchProjectTool
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.tree_service import create_entity

from ._agent_tools_support import _ctx, seed

pytestmark = pytest.mark.integration

__all__ = ["seed"]


async def test_locate_section(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    result = await LocateSectionTool().run(LocateSectionArgs(name="introduction"), ctx)
    assert result.ok and result.data is not None
    matches = result.data["matches"]
    assert len(matches) == 1  # AC1
    m = matches[0]
    # Structure-aware parser (spec 48): 1-based lines; section ends before the next peer.
    assert m["title"] == "Introduction" and m["heading_line"] == 3
    assert m["start_line"] == 3 and m["end_line"] == 4 and m["level"] == "section"
    assert result.data["method"] == "structure-v1"


async def test_search_project(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    result = await SearchProjectTool().run(SearchProjectArgs(query="introduction"), ctx)
    assert result.ok and result.data is not None
    kinds = {m["kind"] for m in result.data["matches"]}
    assert "section" in kinds and "content" in kinds  # AC2
    assert all(m["path"] == "main.tex" for m in result.data["matches"])
    # ranked: section before content
    assert result.data["matches"][0]["kind"] == "section"


async def test_read_file_truncation_and_window(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    big = await create_entity(db_session, seed.project_id, TreeEntityType.doc, "big.tex", None)
    await set_content_from_collab(db_session, big.id, "\n".join(f"line {i}" for i in range(1000)))
    await db_session.commit()
    ctx = _ctx(db_session, seed.project_id, seed.owner.id, agent_tool_read_max_chars=50)

    whole = await ReadFileTool().run(ReadFileArgs(doc_id=str(big.id)), ctx)
    assert whole.ok and whole.data is not None
    assert whole.data["truncated"] is True and whole.data["line_count"] == 1000  # AC3
    assert len(whole.data["content"]) <= 50

    # A window that fits the cap returns exactly that slice, untruncated.
    roomy = _ctx(db_session, seed.project_id, seed.owner.id, agent_tool_read_max_chars=40000)
    window = await ReadFileTool().run(
        ReadFileArgs(doc_id=str(big.id), start_line=10, end_line=20), roomy
    )
    assert window.ok and window.data is not None
    assert window.data["truncated"] is False
    assert window.data["content"].splitlines() == [f"line {i}" for i in range(10, 20)]


async def test_list_tree(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed.project_id, seed.owner.id)
    result = await ListTreeTool().run(ListTreeArgs(depth=2), ctx)
    assert result.ok and result.data is not None
    nodes = result.data["nodes"]
    main = next(n for n in nodes if n["path"] == "main.tex")  # AC4
    assert main["type"] == "doc" and "node_id" in main and main["is_binary"] is False
