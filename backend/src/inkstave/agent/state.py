"""Agent graph state + (de)serialization (spec 41)."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from inkstave.agent.edits import StagedEdit
from inkstave.agent.llm.base import LLMMessage, LLMUsage, ToolCall


def _sum_usage(a: LLMUsage, b: LLMUsage) -> LLMUsage:
    return LLMUsage(
        prompt=a.prompt + b.prompt,
        completion=a.completion + b.completion,
        total=a.total + b.total,
    )


class AgentState(TypedDict, total=False):
    session_id: str
    project_id: str
    user_id: str
    # The running transcript. The reducer appends, so nodes return only new messages.
    messages: Annotated[list[LLMMessage], operator.add]
    pending_tool_calls: list[ToolCall]
    iterations: int
    total_tokens: int
    # Accumulated full usage (prompt/completion/total) across the turn's LLM calls.
    # NOTE: `usage` is forward-wired for specs 42/43 (token accounting consumed by
    # later turn/diff handling); intentionally introduced ahead of the strict
    # spec-41 boundary because specs 42/43 build on this same state object.
    usage: Annotated[LLMUsage, _sum_usage]
    # Edit intents staged by `propose_edit` (spec 42); consumed by spec 43. Reducer appends.
    # NOTE: `staged_edits` is a spec-42 concept forward-wired here so specs 42/43
    # can build on the same `AgentState` without re-shaping it; spec 41 itself
    # leaves it empty. Do not remove — later specs depend on it.
    staged_edits: Annotated[list[StagedEdit], operator.add]
    final_response: str | None
    error: str | None


def serialize_state(state: AgentState) -> dict[str, Any]:
    """A JSON-able snapshot for persistence / the spec-44 event stream."""
    return {
        "session_id": state.get("session_id"),
        "project_id": state.get("project_id"),
        "user_id": state.get("user_id"),
        "messages": [m.model_dump() for m in state.get("messages", [])],
        "pending_tool_calls": [tc.model_dump() for tc in state.get("pending_tool_calls", [])],
        "iterations": state.get("iterations", 0),
        "total_tokens": state.get("total_tokens", 0),
        "usage": state.get("usage", LLMUsage()).model_dump(),
        "staged_edits": [e.model_dump() for e in state.get("staged_edits", [])],
        "final_response": state.get("final_response"),
        "error": state.get("error"),
    }


def deserialize_state(data: dict[str, Any]) -> AgentState:
    state: AgentState = {
        "messages": [LLMMessage.model_validate(m) for m in data.get("messages", [])],
        "pending_tool_calls": [
            ToolCall.model_validate(tc) for tc in data.get("pending_tool_calls", [])
        ],
        "iterations": data.get("iterations", 0),
        "total_tokens": data.get("total_tokens", 0),
        "usage": LLMUsage.model_validate(data.get("usage", {})),
        "staged_edits": [StagedEdit.model_validate(e) for e in data.get("staged_edits", [])],
        "final_response": data.get("final_response"),
        "error": data.get("error"),
    }
    for key in ("session_id", "project_id", "user_id"):
        if data.get(key) is not None:
            state[key] = data[key]  # type: ignore[literal-required]
    return state
