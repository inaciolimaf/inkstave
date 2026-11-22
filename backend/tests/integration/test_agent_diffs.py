"""Integration tests for materialize_diffs (spec 43)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.diffs import materialize_diffs
from inkstave.modules.agent.diffs import repository as diff_repo
from inkstave.modules.agent.diffs.models import ProposedDiff, ProposedDiffStatus
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.graph.edits import StagedEdit
from inkstave.modules.agent.graph.state import AgentState
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import get_document, set_content_from_collab
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_CONTENT = "line0\nline1\nline2\nline3\nline4\n"


@pytest.fixture
async def seed(db_session: AsyncSession) -> SimpleNamespace:
    owner = await UserFactory.create(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    main = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, main.id, _CONTENT)
    session = await agent_repo.create_session(
        db_session, project_id=project.id, user_id=owner.id, model="fake/model"
    )
    await db_session.flush()
    return SimpleNamespace(project=project, main_id=main.id, session=session)


def _edit(doc_id: str, old_text: str, new_text: str) -> StagedEdit:
    return StagedEdit(
        edit_id="e", doc_id=doc_id, path="main.tex", base_version="0", old_text=old_text, new_text=new_text
    )


async def _materialize(
    db: AsyncSession, seed: SimpleNamespace, edits: list[StagedEdit], **settings_over: Any
) -> list[ProposedDiff]:
    state = cast(AgentState, {"staged_edits": edits})
    return await materialize_diffs(
        state=state,
        settings=AgentSettings(**settings_over),
        db=db,
        session=seed.session,
        message_id=None,
    )


async def test_replacement_creates_row_and_leaves_doc(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    edit = _edit(str(seed.main_id), "line1\n", "NEW1\nNEW2\n")
    diffs = await _materialize(db_session, seed, [edit])

    assert len(diffs) == 1  # AC1
    diff = diffs[0]
    assert diff.status == ProposedDiffStatus.proposed.value
    assert diff.diff_text.startswith("--- a/main.tex")
    assert diff.stats["hunk_count"] >= 1
    assert diff.hunks[0]["hunk_id"] == "h1"
    # Document content is unchanged in the DB.
    after = (await get_document(db_session, seed.project.id, seed.main_id)).content
    assert after == _CONTENT


async def test_whole_text_replacement_diff(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    diffs = await _materialize(db_session, seed, [_edit(str(seed.main_id), _CONTENT, "all\nnew\n")])
    assert len(diffs) == 1 and diffs[0].stats["hunk_count"] >= 1  # AC2


async def test_successive_edits_to_one_doc_make_one_proposal(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    edits = [
        _edit(str(seed.main_id), "line0\n", "zero\n"),
        _edit(str(seed.main_id), "zero\nline1", "ZERO\nLINE1"),
    ]
    diffs = await _materialize(db_session, seed, edits)
    assert len(diffs) == 1 and diffs[0].status == ProposedDiffStatus.proposed.value
    # One proposal whose diff is the net effect of both edits on the original text.
    lines = [line for hunk in diffs[0].hunks for line in hunk["lines"]]
    assert [x["text"] for x in lines if x["op"] == "-"] == ["line0", "line1"]
    assert [x["text"] for x in lines if x["op"] == "+"] == ["ZERO", "LINE1"]


async def test_superseding_prior_proposal(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    await _materialize(db_session, seed, [_edit(str(seed.main_id), "line0", "A")])
    await _materialize(db_session, seed, [_edit(str(seed.main_id), "line0", "B")])

    rows = await diff_repo.list_for_session(db_session, seed.session.id)
    statuses = sorted(r.status for r in rows)
    assert statuses == ["proposed", "superseded"]  # AC7


async def test_oversized_doc_is_skipped(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    edit = _edit(str(seed.main_id), _CONTENT, "x" * 100)
    diffs = await _materialize(db_session, seed, [edit], agent_diff_max_doc_chars=5)
    assert diffs == []  # AC9: no row for an oversized doc


async def test_edit_that_no_longer_fits_is_rejected(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    # The second edit's old_text is gone once the first has applied: a rejected row, never a guess.
    edits = [
        _edit(str(seed.main_id), "line1", "X"),
        _edit(str(seed.main_id), "line1", "Y"),
    ]
    diffs = await _materialize(db_session, seed, edits)
    assert len(diffs) == 1 and diffs[0].status == ProposedDiffStatus.rejected.value  # AC4
    assert "could not be applied" in (diffs[0].rationale or "")
    after = (await get_document(db_session, seed.project.id, seed.main_id)).content
    assert after == _CONTENT  # no mutation


async def test_noop_edit_creates_no_row(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    # Replacing "line1" with itself changes nothing.
    edit = _edit(str(seed.main_id), "line1", "line1")
    diffs = await _materialize(db_session, seed, [edit])
    assert diffs == []  # AC5
