"""In-process turn runner (spec 41). Spec 44's ARQ job will call ``run_turn``."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from inkstave.core.db.session import allow_idle
from inkstave.modules.agent.diffs import materialize_diffs
from inkstave.modules.agent.file_ops import materialize_file_ops
from inkstave.modules.agent.graph import repository as repo
from inkstave.modules.agent.graph.builder import build_graph
from inkstave.modules.agent.graph.prompts import PromptContext, build_system_prompt
from inkstave.modules.agent.graph.state import AgentState
from inkstave.modules.agent.llm.base import LLMMessage, LLMUsage, ToolCall
from inkstave.modules.agent.tools.base import ToolContext

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.agent.diffs.models import ProposedDiff
    from inkstave.modules.agent.file_ops import ProposedFileOp
    from inkstave.modules.agent.graph.agent_deps import AgentDeps
    from inkstave.modules.agent.graph.edits import StagedEdit
    from inkstave.modules.agent.models import AgentSession


@dataclass
class AgentTurnResult:
    final_response: str | None
    messages_added: int
    usage: LLMUsage
    iterations: int
    error: str | None
    staged_edits: list[StagedEdit] = field(default_factory=list)
    proposed_diffs: list[ProposedDiff] = field(default_factory=list)
    proposed_file_ops: list[ProposedFileOp] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)


def _to_llm_message(
    role: str, content: str | None, tool_calls: object, tool_call_id: str | None
) -> LLMMessage:
    calls = [ToolCall.model_validate(tc) for tc in tool_calls] if isinstance(tool_calls, list) else None
    return LLMMessage(
        role=role,
        content=content,
        tool_calls=calls,
        tool_call_id=tool_call_id,
    )


async def _build_transcript(db: AsyncSession, session: AgentSession, user_message: str) -> list[LLMMessage]:
    """A freshly-computed system prompt (never persisted) + stored history + input."""
    prior = await repo.list_messages(db, session.id)
    system = build_system_prompt(PromptContext(project_id=str(session.project_id)))
    transcript: list[LLMMessage] = [LLMMessage(role="system", content=system)]
    transcript.extend(_to_llm_message(m.role, m.content, m.tool_calls, m.tool_call_id) for m in prior)
    transcript.append(LLMMessage(role="user", content=user_message))
    return transcript


def _initial_state(session: AgentSession, transcript: list[LLMMessage]) -> AgentState:
    return {
        "session_id": str(session.id),
        "project_id": str(session.project_id),
        "user_id": str(session.user_id),
        "messages": transcript,
        "pending_tool_calls": [],
        "iterations": 0,
        "total_tokens": 0,
        "usage": LLMUsage(),
        "staged_edits": [],
        "staged_file_ops": [],
        "final_response": None,
        "error": None,
    }


async def _persist_produced(
    db: AsyncSession,
    session: AgentSession,
    produced: list[LLMMessage],
    *,
    first_seq: int,
    usage: LLMUsage,
) -> UUID | None:
    """Write the turn's new messages in order; return the last assistant row's id.

    The turn's aggregate usage is recorded on that last assistant row only.
    """
    last_idx = max((i for i, m in enumerate(produced) if m.role == "assistant"), default=-1)
    last_assistant_id: UUID | None = None
    for offset, message in enumerate(produced):
        row = await repo.add_message(
            db,
            session_id=session.id,
            seq=first_seq + offset,
            role=message.role,
            content=message.content,
            tool_calls=([tc.model_dump() for tc in message.tool_calls] if message.tool_calls else None),
            tool_call_id=message.tool_call_id,
            token_usage=usage.model_dump() if offset == last_idx else None,
        )
        if offset == last_idx:
            last_assistant_id = row.id
    return last_assistant_id


def _tool_context(db: AsyncSession, session: AgentSession, deps: AgentDeps) -> ToolContext:
    """Scoped to this session's project, carrying the DB session tools run against (spec 42)."""
    return ToolContext(
        db=db,
        project_id=str(session.project_id),
        user_id=str(session.user_id),
        settings=deps.settings,
        injection_guard=deps.injection_guard,
        object_store=deps.object_store,
    )


async def _touch_session(db: AsyncSession, session: AgentSession, user_message: str) -> None:
    """Keep the session ordered by recency and give it a title on the first turn."""
    if session.title is None:
        session.title = user_message[:80]
    session.updated_at = datetime.now(UTC)
    await db.flush()


async def _store_proposals(
    state: AgentState, deps: AgentDeps, db: AsyncSession, session: AgentSession, message_id: UUID | None
) -> tuple[list[ProposedDiff], list[ProposedFileOp]]:
    """Turn the turn's staged work into rows the user reviews, attributed to its last message."""
    diffs = await materialize_diffs(
        state=state, settings=deps.settings, db=db, session=session, message_id=message_id
    )
    file_ops = await materialize_file_ops(state=state, db=db, session=session, message_id=message_id)
    return diffs, file_ops


async def run_turn(
    *,
    session: AgentSession,
    user_message: str,
    deps: AgentDeps,
    db: AsyncSession,
) -> AgentTurnResult:
    # The whole turn is one transaction, so its model calls happen inside it: a failed turn
    # leaves no trace of its messages. It cannot end early, so it gets the job's whole budget.
    await allow_idle(db, deps.settings.agent_job_timeout_s)

    # 1. Build the transcript from the stored history + the new user message.
    transcript = await _build_transcript(db, session, user_message)

    # 2/3. Persist the user message row (next seq).
    seq = await repo.next_seq(db, session.id)
    await repo.add_message(db, session_id=session.id, seq=seq, role="user", content=user_message)

    # 4. Run the graph to completion.
    tool_ctx = _tool_context(db, session, deps)
    graph = build_graph(replace(deps, tool_context=tool_ctx))
    result = cast(AgentState, await graph.ainvoke(_initial_state(session, transcript)))

    # 5. Persist everything the turn appended after the input transcript, in order.
    produced = result["messages"][len(transcript) :]
    usage = result.get("usage", LLMUsage())
    last_assistant_id = await _persist_produced(db, session, produced, first_seq=seq + 1, usage=usage)

    # 6. Store what the turn proposed. Nothing in the project changes.
    proposed_diffs, proposed_file_ops = await _store_proposals(result, deps, db, session, last_assistant_id)

    await _touch_session(db, session, user_message)
    return AgentTurnResult(
        final_response=result.get("final_response"),
        messages_added=1 + len(produced),
        usage=usage,
        iterations=result.get("iterations", 0),
        error=result.get("error"),
        staged_edits=list(result.get("staged_edits", [])),
        proposed_diffs=proposed_diffs,
        proposed_file_ops=proposed_file_ops,
        audit_events=list(tool_ctx.audit_events),
    )
