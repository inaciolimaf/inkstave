"""Shared helpers/fixtures for the agent tools integration tests (spec 42)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent import repository as agent_repo
from inkstave.agent.llm.base import LLMResponse, ToolCall
from inkstave.agent.settings import AgentSettings
from inkstave.agent.tools.base import ToolContext
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.factories import UserFactory

_MAIN = "\n".join(
    [
        r"\documentclass{article}",  # 0
        r"\begin{document}",  # 1
        r"\section{Introduction}",  # 2
        "This is the introduction. It discusses motivation.",  # 3
        r"\section{Methods}",  # 4
        "We describe the methods here.",  # 5
        r"\end{document}",  # 6
    ]
)


async def _member(db: AsyncSession, pid: UUID, uid: UUID, role: str) -> None:
    db.add(
        ProjectMembership(project_id=pid, user_id=uid, role=role, status=MembershipStatus.active)
    )
    await db.flush()


@pytest.fixture
async def seed(db_session: AsyncSession) -> SimpleNamespace:
    owner = await UserFactory.create(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    main = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, main.id, _MAIN)
    editor = await UserFactory.create(db_session)
    await _member(db_session, project.id, editor.id, MembershipRole.editor)
    viewer = await UserFactory.create(db_session)
    await _member(db_session, project.id, viewer.id, MembershipRole.viewer)
    await db_session.commit()
    return SimpleNamespace(
        project_id=project.id, owner=owner, editor=editor, viewer=viewer, main_id=main.id
    )


def _ctx(db: AsyncSession, pid: UUID, uid: UUID, **over: Any) -> ToolContext:
    return ToolContext(db=db, project_id=str(pid), user_id=str(uid), settings=AgentSettings(**over))


def _tool_call(name: str, args: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id=uuid4().hex, name=name, arguments=args)],
        finish_reason="tool_calls",
    )


async def _session(db: AsyncSession, seed: SimpleNamespace):
    return await agent_repo.create_session(
        db, project_id=seed.project_id, user_id=seed.owner.id, model="fake/model"
    )
