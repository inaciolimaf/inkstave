"""Integration tests for propose_edit's read guard and exact-text matching (spec 42, spec 43).

Each test drives the tools directly against a real document, so the document's version and
text are the database's. The model-facing flow is covered by the evals in
``tests/agent_evals/test_agent_evals.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.diffs import materialize_diffs
from inkstave.modules.agent.diffs.models import ProposedDiffStatus
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.tools.base import ToolContext
from inkstave.modules.agent.tools.propose_edit import ProposeEditArgs, ProposeEditTool
from inkstave.modules.agent.tools.read_file import ReadFileArgs, ReadFileTool
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import get_document, set_content_from_collab
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.factories import UserFactory
from tests.fixtures.unified import apply_unified

pytestmark = pytest.mark.integration

_CONTENT = "alpha\nbeta\ngamma\n"


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
    return SimpleNamespace(owner=owner, project=project, doc_id=str(main.id), session=session)


def _ctx(db: AsyncSession, seed: SimpleNamespace) -> ToolContext:
    return ToolContext(
        db=db, project_id=str(seed.project.id), user_id=str(seed.owner.id), settings=AgentSettings()
    )


async def _read(ctx: ToolContext, doc_id: str) -> Any:
    return await ReadFileTool().run(ReadFileArgs(doc_id=doc_id), ctx)


async def _propose(ctx: ToolContext, doc_id: str, old_text: str, new_text: str) -> Any:
    args = ProposeEditArgs(doc_id=doc_id, old_text=old_text, new_text=new_text)
    return await ProposeEditTool().run(args, ctx)


async def test_propose_without_reading_is_refused(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed)
    result = await _propose(ctx, seed.doc_id, "beta", "BETA")
    assert not result.ok and result.error is not None
    assert result.error.message == "read_file this document before proposing an edit."
    assert ctx.staged_edits == []


async def test_read_then_propose_succeeds(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed)
    read = await _read(ctx, seed.doc_id)
    assert read.ok and read.data is not None and read.data["content"] == _CONTENT  # exact text, no numbers

    result = await _propose(ctx, seed.doc_id, "beta", "BETA")
    assert result.ok and result.data is not None and result.data["staged"] is True
    assert len(ctx.staged_edits) == 1


async def test_a_read_in_another_turn_does_not_count(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    await _read(_ctx(db_session, seed), seed.doc_id)  # an earlier turn's context
    result = await _propose(_ctx(db_session, seed), seed.doc_id, "beta", "BETA")
    assert not result.ok and result.error is not None
    assert result.error.message == "read_file this document before proposing an edit."


async def test_change_since_read_is_refused(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    await set_content_from_collab(db_session, UUID(seed.doc_id), "alpha\nBETA\ngamma\n")  # bumps the version

    result = await _propose(ctx, seed.doc_id, "beta", "x")
    assert not result.ok and result.error is not None
    assert result.error.message == "the file changed since you read it; read_file again."
    assert ctx.staged_edits == []


async def test_old_text_missing_is_refused(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    result = await _propose(ctx, seed.doc_id, "delta", "x")
    assert not result.ok and result.error is not None and result.error.code == "invalid_args"
    assert (
        result.error.message
        == "old_text not found in the current file; read_file again and copy the exact text."
    )


async def test_old_text_repeated_is_refused_with_the_count(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    await set_content_from_collab(db_session, UUID(seed.doc_id), "x\nx\nx\n")
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    result = await _propose(ctx, seed.doc_id, "x", "y")
    assert not result.ok and result.error is not None
    assert "occurs 3 times" in result.error.message
    assert ctx.staged_edits == []


async def test_empty_old_text_only_fills_an_empty_file(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    refused = await _propose(ctx, seed.doc_id, "", "new\n")
    assert not refused.ok and refused.error is not None and "empty file" in refused.error.message

    await set_content_from_collab(db_session, UUID(seed.doc_id), "")
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    filled = await _propose(ctx, seed.doc_id, "", "new\n")
    assert filled.ok and ctx.staged_edits[0].new_text == "new\n"


async def test_identical_text_is_refused(seed: SimpleNamespace, db_session: AsyncSession) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    result = await _propose(ctx, seed.doc_id, "beta", "beta")
    assert not result.ok and result.error is not None and "nothing to change" in result.error.message


async def test_two_edits_to_one_doc_apply_in_sequence(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    assert (await _propose(ctx, seed.doc_id, "alpha", "ALPHA")).ok
    assert (await _propose(ctx, seed.doc_id, "gamma", "GAMMA")).ok

    # The text the next edit must match is the text after the first edit, not the stored one.
    reread = await _read(ctx, seed.doc_id)
    assert reread.data is not None and reread.data["content"] == "ALPHA\nbeta\nGAMMA\n"
    assert reread.data["proposed_edits"] == 2
    stale = await _propose(ctx, seed.doc_id, "alpha", "again")
    assert not stale.ok and stale.error is not None and "not found" in stale.error.message


async def test_the_proposed_diff_applies_to_the_current_text(
    seed: SimpleNamespace, db_session: AsyncSession
) -> None:
    ctx = _ctx(db_session, seed)
    await _read(ctx, seed.doc_id)
    await _propose(ctx, seed.doc_id, "alpha", "ALPHA")
    await _propose(ctx, seed.doc_id, "beta\ngamma", "BETA\nGAMMA\nDELTA")

    diffs = await materialize_diffs(
        state={"staged_edits": ctx.staged_edits},
        settings=AgentSettings(),
        db=db_session,
        session=seed.session,
        message_id=None,
    )
    assert len(diffs) == 1 and diffs[0].status == ProposedDiffStatus.proposed.value
    current = (await get_document(db_session, seed.project.id, UUID(seed.doc_id))).content
    assert apply_unified(current, diffs[0].diff_text) == "ALPHA\nBETA\nGAMMA\nDELTA\n"
    assert current == _CONTENT  # the document itself is untouched
