"""The agent reads a lived-in project: read_file and search_project see the content that already exists.

Only read tools are used here; the write tools are covered by their own suites.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.tools.base import ToolContext
from inkstave.modules.agent.tools.read_file import ReadFileArgs, ReadFileTool
from inkstave.modules.agent.tools.search_project import SearchProjectArgs, SearchProjectTool
from tests.factories.lived_in import INTRO_TEX, MAIN_TEX, LivedInProject
from tests.integration._seeded_support import auth_headers

pytestmark = pytest.mark.integration


def _ctx(db: AsyncSession, lived: LivedInProject) -> ToolContext:
    return ToolContext(
        db=db, project_id=str(lived.project_id), user_id=str(lived.owner.id), settings=AgentSettings()
    )


async def test_seeded_read_file_by_path_returns_existing_content(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    result = await ReadFileTool().run(
        ReadFileArgs(path="chapters/intro.tex"), _ctx(db_session, lived_in_project)
    )

    assert result.ok
    assert result.data is not None
    assert result.data["path"] == "chapters/intro.tex"
    assert result.data["content"] == INTRO_TEX


async def test_seeded_read_file_by_id_reads_the_root_document(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    result = await ReadFileTool().run(
        ReadFileArgs(doc_id=str(lived_in_project.main_id)), _ctx(db_session, lived_in_project)
    )

    assert result.ok
    assert result.data is not None
    assert result.data["content"] == MAIN_TEX


async def test_seeded_read_file_window_of_an_older_document(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    result = await ReadFileTool().run(
        ReadFileArgs(path="appendix.tex", start_line=1, end_line=2), _ctx(db_session, lived_in_project)
    )

    assert result.ok
    assert result.data is not None
    assert result.data["content"] == "\\section{Legacy notes}\n"


async def test_seeded_search_project_finds_text_in_every_seeded_document(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    ctx = _ctx(db_session, lived_in_project)

    cite = await SearchProjectTool().run(SearchProjectArgs(query="knuth84"), ctx)
    seeded = await SearchProjectTool().run(SearchProjectArgs(query="seeded before"), ctx)

    assert cite.ok and seeded.ok
    assert cite.data is not None and seeded.data is not None
    cite_paths = {match["path"] for match in cite.data["matches"]}
    assert cite_paths == {"chapters/methods.tex", "refs.bib"}
    assert {match["path"] for match in seeded.data["matches"]} == {"chapters/intro.tex"}


async def test_seeded_read_file_unknown_path_is_not_found(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    result = await ReadFileTool().run(ReadFileArgs(path="missing.tex"), _ctx(db_session, lived_in_project))

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "not_found"


async def test_seeded_pending_proposal_is_listed_for_its_session(
    async_client: AsyncClient, lived_in_project: LivedInProject
) -> None:
    headers = auth_headers(lived_in_project.owner)
    url = f"/api/v1/projects/{lived_in_project.project_id}/agent/sessions/{lived_in_project.session_id}/diffs"

    resp = await async_client.get(url, headers=headers)

    assert resp.status_code == 200
    proposals = resp.json()
    assert [p["id"] for p in proposals] == [str(lived_in_project.proposal_id)]
    assert proposals[0]["status"] == "proposed"
    assert proposals[0]["path"] == "chapters/intro.tex"
    assert proposals[0]["stats"]["additions"] == 1
    assert proposals[0]["stats"]["deletions"] == 1
    assert proposals[0]["message_id"] is not None  # placed after the agent's reply in the transcript
