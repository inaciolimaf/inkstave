"""Integration tests for materialize_diffs (spec 43)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent import repository as agent_repo
from inkstave.agent.diffs import materialize_diffs
from inkstave.agent.diffs import repository as diff_repo
from inkstave.agent.diffs.models import ProposedDiffStatus
from inkstave.agent.edits import EditMode, StagedEdit
from inkstave.agent.settings import AgentSettings
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import get_document, set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
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


def _edit(doc_id: str, mode: str, new_text: str, start=None, end=None) -> StagedEdit:
    return StagedEdit(
        edit_id="e", doc_id=doc_id, path="main.tex", base_version="0", mode=EditMode(mode),
        new_text=new_text, start_line=start, end_line=end,
    )


async def _materialize(db, seed, edits, **settings_over):
    state = {"staged_edits": edits}
    return await materialize_diffs(
        state=state, settings=AgentSettings(**settings_over), db=db,
        session=seed.session, message_id=None,
    )


async def test_range_edit_creates_row_and_leaves_doc(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    edit = _edit(str(seed.main_id), "range", "NEW1\nNEW2", start=3, end=5)
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


async def test_full_edit_diff(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    diffs = await _materialize(db_session, seed, [_edit(str(seed.main_id), "full", "all\nnew\n")])
    assert len(diffs) == 1 and diffs[0].stats["hunk_count"] >= 1  # AC2


async def test_superseding_prior_proposal(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    await _materialize(db_session, seed, [_edit(str(seed.main_id), "range", "A", start=0, end=1)])
    await _materialize(db_session, seed, [_edit(str(seed.main_id), "range", "B", start=0, end=1)])

    rows = await diff_repo.list_for_session(db_session, seed.session.id)
    statuses = sorted(r.status for r in rows)
    assert statuses == ["proposed", "superseded"]  # AC7


async def test_oversized_doc_is_skipped(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    edit = _edit(str(seed.main_id), "full", "x" * 100)
    diffs = await _materialize(db_session, seed, [edit], agent_diff_max_doc_chars=5)
    assert diffs == []  # AC9: no row for an oversized doc


async def test_overlapping_ranges_rejected(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    edits = [
        _edit(str(seed.main_id), "range", "X", start=1, end=3),
        _edit(str(seed.main_id), "range", "Y", start=2, end=4),
    ]
    diffs = await _materialize(db_session, seed, edits)
    assert len(diffs) == 1 and diffs[0].status == ProposedDiffStatus.rejected.value  # AC4
    after = (await get_document(db_session, seed.project.id, seed.main_id)).content
    assert after == _CONTENT  # no mutation


async def test_noop_edit_creates_no_row(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    # Replace line 1 ("line1") with its exact current content → no change.
    edit = _edit(str(seed.main_id), "range", "line1", start=1, end=2)
    diffs = await _materialize(db_session, seed, [edit])
    assert diffs == []  # AC5
