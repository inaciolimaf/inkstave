"""Integration tests for the agent runner + repository (spec 41)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent import repository as repo
from inkstave.agent.deps import AgentDeps
from inkstave.agent.llm.fake import FakeLLM
from inkstave.agent.runner import run_turn
from inkstave.agent.settings import AgentSettings
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


def _deps(*responses: object) -> AgentDeps:
    return AgentDeps(llm=FakeLLM(script=list(responses)), settings=AgentSettings())


async def _session(db: AsyncSession):
    user = await UserFactory.create(db)
    project = await create_project(db, user.id, "Paper")
    await db.flush()
    return await repo.create_session(db, project_id=project.id, user_id=user.id, model="fake/model")


async def test_run_turn_persists_user_and_assistant_with_usage(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    deps = _deps(FakeLLM.respond_text("Hello there", prompt=3, completion=4))

    result = await run_turn(session=session, user_message="Help me", deps=deps, db=db_session)

    assert result.final_response == "Hello there"  # AC3
    assert result.messages_added == 2 and result.iterations == 1
    assert result.usage.total == 7

    rows = await repo.list_messages(db_session, session.id)
    assert [(r.seq, r.role, r.content) for r in rows] == [
        (0, "user", "Help me"),
        (1, "assistant", "Hello there"),
    ]
    assert rows[1].token_usage == {"prompt": 3, "completion": 4, "total": 7}
    # No system prompt is ever persisted.
    assert all(r.role != "system" for r in rows)
    assert session.title == "Help me"  # titled from the first message


async def test_two_turns_keep_seq_contiguous_no_system_dup(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    deps = _deps(
        FakeLLM.respond_text("First reply"),
        FakeLLM.respond_text("Second reply"),
    )

    await run_turn(session=session, user_message="one", deps=deps, db=db_session)
    r2 = await run_turn(session=session, user_message="two", deps=deps, db=db_session)
    assert r2.final_response == "Second reply"

    rows = await repo.list_messages(db_session, session.id)
    assert [r.seq for r in rows] == [0, 1, 2, 3]  # AC9: contiguous + unique
    assert [r.role for r in rows] == ["user", "assistant", "user", "assistant"]
    assert all(r.role != "system" for r in rows)  # system prompt not duplicated in storage


async def test_repository_crud_and_ordering(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    project = await create_project(db_session, user.id, "P")
    await db_session.flush()
    session = await repo.create_session(
        db_session, project_id=project.id, user_id=user.id, model="m", title="t"
    )
    await repo.add_message(db_session, session_id=session.id, seq=0, role="user", content="a")
    await repo.add_message(db_session, session_id=session.id, seq=1, role="assistant", content="b")

    assert await repo.next_seq(db_session, session.id) == 2
    listed = await repo.list_sessions(db_session, project_id=project.id, user_id=user.id)
    assert [s.id for s in listed] == [session.id]
    msgs = await repo.list_messages(db_session, session.id)
    assert [m.content for m in msgs] == ["a", "b"]


async def test_duplicate_seq_rejected(db_session: AsyncSession) -> None:
    session = await _session(db_session)
    await repo.add_message(db_session, session_id=session.id, seq=0, role="user", content="a")
    with pytest.raises(IntegrityError):  # add_message flushes, surfacing the unique violation
        await repo.add_message(db_session, session_id=session.id, seq=0, role="user", content="dup")
