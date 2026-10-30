"""Shared helpers/fixtures for the agent HTTP API integration tests (spec 44)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.core.config.settings import get_settings
from inkstave.modules.agent.deps import get_agent_enqueuer
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.llm.base import LLMResponse, ToolCall
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.models import AgentRunState, AgentSession
from inkstave.modules.agent.runs.events import InMemoryEventSink
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import set_content_from_collab
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.factories import UserFactory

API = "/api/v1/projects"


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue(self, *, session_id: UUID, run_id: UUID, user_message: str) -> str | None:
        self.calls.append({"session_id": session_id, "run_id": run_id, "msg": user_message})
        return "job"


@pytest.fixture
def enqueuer(app: Any) -> _FakeEnqueuer:
    fake = _FakeEnqueuer()
    app.dependency_overrides[get_agent_enqueuer] = lambda: fake
    return fake


async def _auth(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seed(db_session: AsyncSession) -> SimpleNamespace:
    owner = await UserFactory.create(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    main = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, main.id, "line0\nline1\nline2\n")
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(owner)
    return SimpleNamespace(
        owner=owner, project=project, main_id=main.id, headers={"Authorization": f"Bearer {token}"}
    )


def _job_ctx(db: AsyncSession, redis: Any, llm: FakeLLM, sink: InMemoryEventSink) -> dict[str, Any]:
    return {
        "settings": AgentSettings(),
        "session_factory": lambda: _SessionCtx(db),
        "redis": redis,
        "llm_client": llm,
        "event_sink": sink,
    }


def _tool_call(name: str, args: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id=uuid4().hex, name=name, arguments=args)], finish_reason="tool_calls"
    )


async def _make_session(db: AsyncSession, seed: SimpleNamespace) -> AgentSession:
    session = await agent_repo.create_session(
        db, project_id=seed.project.id, user_id=seed.owner.id, model="fake/model"
    )
    session.active_run_id = uuid4()
    session.run_state = AgentRunState.queued.value
    await db.flush()
    return session
