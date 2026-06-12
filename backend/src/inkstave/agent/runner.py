"""In-process turn runner (spec 41). Spec 44's ARQ job will call ``run_turn``."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from inkstave.agent import repository as repo
from inkstave.agent.diffs import materialize_diffs
from inkstave.agent.graph import build_graph
from inkstave.agent.llm.base import LLMMessage, LLMUsage, ToolCall
from inkstave.agent.prompts import PromptContext, build_system_prompt
from inkstave.agent.state import AgentState
from inkstave.agent.tools.base import ToolContext

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.agent.deps import AgentDeps
    from inkstave.agent.diffs.models import ProposedDiff
    from inkstave.agent.edits import StagedEdit
    from inkstave.agent.models import AgentSession


@dataclass
class AgentTurnResult:
    final_response: str | None
    messages_added: int
    usage: LLMUsage
    iterations: int
    error: str | None
    staged_edits: list[StagedEdit] = field(default_factory=list)
    proposed_diffs: list[ProposedDiff] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)


def _to_llm_message(
    role: str, content: str | None, tool_calls: object, tool_call_id: str | None
) -> LLMMessage:
    calls = (
        [ToolCall.model_validate(tc) for tc in tool_calls] if isinstance(tool_calls, list) else None
    )
    return LLMMessage(
        role=role,  # type: ignore[arg-type]
        content=content,
        tool_calls=calls,
        tool_call_id=tool_call_id,
    )


async def run_turn(
    *,
    session: AgentSession,
    user_message: str,
    deps: AgentDeps,
    db: AsyncSession,
) -> AgentTurnResult:
    # 1. Build the transcript: a freshly-computed system prompt (never persisted) +
    #    the stored history + the new user message.
    prior = await repo.list_messages(db, session.id)
    system = build_system_prompt(PromptContext(project_id=str(session.project_id)))
    transcript: list[LLMMessage] = [LLMMessage(role="system", content=system)]
    transcript.extend(
        _to_llm_message(m.role, m.content, m.tool_calls, m.tool_call_id) for m in prior
    )
    transcript.append(LLMMessage(role="user", content=user_message))

    # 2/3. Persist the user message row (next seq).
    seq = await repo.next_seq(db, session.id)
    await repo.add_message(db, session_id=session.id, seq=seq, role="user", content=user_message)
    seq += 1

    # 4. Run the graph to completion. The tool context is scoped to this session's
    #    project and carries the DB session tools execute against (spec 42).
    tool_ctx = ToolContext(
        db=db,
        project_id=str(session.project_id),
        user_id=str(session.user_id),
        settings=deps.settings,
        injection_guard=deps.injection_guard,
    )
    turn_deps = replace(deps, tool_context=tool_ctx)
    initial: AgentState = {
        "session_id": str(session.id),
        "project_id": str(session.project_id),
        "user_id": str(session.user_id),
        "messages": transcript,
        "pending_tool_calls": [],
        "iterations": 0,
        "total_tokens": 0,
        "usage": LLMUsage(),
        "staged_edits": [],
        "final_response": None,
        "error": None,
    }
    result = cast(AgentState, await build_graph(turn_deps).ainvoke(initial))

    # 5. Persist the messages this turn produced (everything appended after the input
    #    transcript), in order. The turn's aggregate usage goes on the last assistant row.
    produced = result["messages"][len(transcript) :]
    usage = result.get("usage", LLMUsage())
    last_assistant_idx = max(
        (i for i, m in enumerate(produced) if m.role == "assistant"), default=-1
    )
    last_assistant_id: UUID | None = None
    for offset, message in enumerate(produced):
        row = await repo.add_message(
            db,
            session_id=session.id,
            seq=seq + offset,
            role=message.role,
            content=message.content,
            tool_calls=[tc.model_dump() for tc in message.tool_calls]
            if message.tool_calls
            else None,
            tool_call_id=message.tool_call_id,
            token_usage=usage.model_dump() if offset == last_assistant_idx else None,
        )
        if offset == last_assistant_idx:
            last_assistant_id = row.id

    # 6. Turn the turn's staged edits into reviewable proposed diffs (spec 43). No
    #    document is mutated; the diffs are attributed to the final assistant message.
    # NOTE: `materialize_diffs` is forward-wired for spec 43 — spec 41 §4 lists diff
    #    generation as a non-goal, but specs 42/43 legitimately build on this same
    #    runner, so the call is introduced here ahead of the strict spec-41 boundary
    #    (with no staged edits it simply returns an empty list). Do not remove.
    proposed_diffs = await materialize_diffs(
        state=result,
        settings=deps.settings,
        db=db,
        session=session,
        message_id=last_assistant_id,
    )

    # Keep the session ordered by recency and give it a title on the first turn.
    if session.title is None:
        session.title = user_message[:80]
    session.updated_at = datetime.now(UTC)
    await db.flush()

    return AgentTurnResult(
        final_response=result.get("final_response"),
        messages_added=1 + len(produced),
        usage=usage,
        iterations=result.get("iterations", 0),
        error=result.get("error"),
        staged_edits=list(result.get("staged_edits", [])),
        proposed_diffs=proposed_diffs,
        audit_events=list(tool_ctx.audit_events),
    )
