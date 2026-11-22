"""Shared pieces of the scenario tests: a project, one turn through the real job, and readers of the result.

A scenario is a scripted model (``inkstave.modules.agent.scripted``) run through the real graph,
the real job and the real persistence. Only the model and the clock are replaced.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.diffs import repository as diff_repo
from inkstave.modules.agent.diffs.models import ProposedDiff
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.models import AgentMessage, AgentRunState, AgentSession
from inkstave.modules.agent.runs.events import InMemoryEventSink
from inkstave.modules.agent.runs.jobs import run_agent_turn
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import get_document, set_content_from_collab
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.factories import UserFactory

MAIN_TEX = "\n".join(
    [
        r"\documentclass{article}",
        r"\begin{document}",
        r"\section{Introduction}",
        "The introduction motivates the work.",
        r"\section{Methods}",
        "We describe the methods here.",
        r"\end{document}",
    ]
)
NOTES_TEX = "Remember to cite the survey.\n"
BINARY_NAME = "logo.png"


class _SessionCtx:
    """The job's ``session_factory`` context: hands the test's own session to the job."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def make_project(db: AsyncSession) -> SimpleNamespace:
    """A project with ``main.tex`` (the paper), ``notes.tex`` and a binary ``logo.png``."""
    owner = await UserFactory.create(db)
    proj = await create_project(db, owner.id, "Paper")
    main = await create_entity(db, proj.id, TreeEntityType.doc, "main.tex", None)
    notes = await create_entity(db, proj.id, TreeEntityType.doc, "notes.tex", None)
    logo = await create_entity(db, proj.id, TreeEntityType.file, BINARY_NAME, None)
    await set_content_from_collab(db, main.id, MAIN_TEX)
    await set_content_from_collab(db, notes.id, NOTES_TEX)
    await db.flush()
    return SimpleNamespace(owner=owner, proj=proj, main_id=main.id, notes_id=notes.id, binary_id=logo.id)


async def new_session(db: AsyncSession, project: SimpleNamespace) -> AgentSession:
    session = await agent_repo.create_session(
        db, project_id=project.proj.id, user_id=project.owner.id, model="scripted/model"
    )
    await db.flush()
    return session


async def queue_run(db: AsyncSession, session: AgentSession) -> UUID:
    """Mark the session as queued for a new run, the way ``post_message`` does."""
    run_id = uuid4()
    session.run_state = AgentRunState.queued.value
    session.active_run_id = run_id
    await db.flush()
    return run_id


async def play_turn(
    db: AsyncSession,
    redis: Any,
    session: AgentSession,
    llm: Any,
    message: str,
    *,
    settings: AgentSettings | None = None,
    run_id: UUID | None = None,
) -> InMemoryEventSink:
    """Run one turn through ``run_agent_turn`` and return the events the panel would have seen."""
    run = run_id or await queue_run(db, session)
    sink = InMemoryEventSink(str(run))
    ctx: dict[str, Any] = {
        "agent_settings": settings or AgentSettings(),
        "session_factory": lambda: _SessionCtx(db),
        "redis": redis,
        "llm_client": llm,
        "event_sink": sink,
    }
    await run_agent_turn(ctx, session_id=str(session.id), run_id=str(run), user_message=message)
    return sink


async def transcript(db: AsyncSession, session: AgentSession) -> list[AgentMessage]:
    return await agent_repo.list_messages(db, session.id)


async def diffs_of(db: AsyncSession, session: AgentSession) -> list[ProposedDiff]:
    return await diff_repo.list_for_session(db, session.id)


async def doc_text(db: AsyncSession, project: SimpleNamespace, entity_id: UUID) -> str:
    document = await get_document(db, project.proj.id, entity_id)
    return document.content


def tool_outcomes(sink: InMemoryEventSink) -> list[tuple[str, bool, str]]:
    """(tool name, ok, summary) of every tool the panel was told about, in order."""
    return [(e["name"], e["ok"], e["summary"]) for e in sink.events if e["type"] == "tool_result"]


def stored_tool_errors(messages: list[AgentMessage]) -> list[str]:
    """The error codes the model was given back, read from the stored tool messages."""
    codes: list[str] = []
    for message in messages:
        if message.role != "tool" or not message.content:
            continue
        error = json.loads(message.content).get("error")
        if error:
            codes.append(error["code"])
    return codes


def terminal(sink: InMemoryEventSink) -> dict[str, Any]:
    return sink.events[-1]


def final_text(sink: InMemoryEventSink) -> str:
    return "".join(e["text"] for e in sink.events if e["type"] == "token")


def unanswered_tool_calls(messages: list[Any]) -> list[str]:
    """Ids of tool calls that have no tool result after them: a provider rejects such a history."""
    answered = {m.tool_call_id for m in messages if m.role == "tool"}
    pending: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            call_id = call.id if hasattr(call, "id") else call["id"]
            if call_id not in answered:
                pending.append(call_id)
    return pending
