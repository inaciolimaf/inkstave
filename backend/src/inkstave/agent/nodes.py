"""Graph node functions: plan / act / observe / respond (spec 41).

These reach the model only through the injected ``LLMClient`` (``deps.llm``) — they
never import the OpenAI SDK. A turn with no tools simply plans then responds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from inkstave.agent.llm.base import LLMError, LLMMessage, LLMUsage
from inkstave.agent.safety.budget import cost_for, run_cost_exceeded, run_tokens_exceeded
from inkstave.agent.safety.injection import flag_injection, wrap_untrusted
from inkstave.agent.state import AgentState
from inkstave.agent.tools.base import ToolResult

if TYPE_CHECKING:
    from inkstave.agent.deps import AgentDeps

logger = logging.getLogger("inkstave.agent")

# Sentinel error values (spec 44 / 49).
CANCELLED = "cancelled"
BUDGET_EXCEEDED = "budget_exceeded"

# User-facing closing text for a terminal error — the raw sentinel / exception string
# is never persisted into the chat transcript (spec 50 refactor).
_ERROR_CLOSINGS = {
    CANCELLED: "Run cancelled.",
    BUDGET_EXCEEDED: "This run reached its token or cost budget.",
}


def _frame_for_llm(messages: list[LLMMessage]) -> list[LLMMessage]:
    """Wrap tool-role content in untrusted framing before it reaches the model (spec 49).

    The stored transcript keeps the raw content; only the LLM input is framed, so a
    tool result can never be read as a system/developer instruction.
    """
    framed: list[LLMMessage] = []
    for m in messages:
        if m.role == "tool" and m.content is not None:
            framed.append(
                m.model_copy(update={"content": wrap_untrusted("tool_result", m.content)})
            )
        else:
            framed.append(m)
    return framed


def _last_assistant_content(messages: list[LLMMessage]) -> str | None:
    for message in reversed(messages):
        if message.role == "assistant" and message.content:
            return message.content
    return None


def _chunk(text: str, size: int = 16) -> list[str]:
    """Slice assistant content into a few token-stream chunks (deterministic)."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


def _result_summary(result: ToolResult) -> str:
    if result.ok:
        keys = sorted((result.data or {}).keys())
        return f"ok: {', '.join(keys)}" if keys else "ok"
    return result.error.message if result.error else "error"


def make_plan(deps: AgentDeps) -> Any:
    settings = deps.settings
    tool_specs = deps.tools.specs() or None

    async def plan(state: AgentState) -> dict[str, Any]:
        if deps.should_cancel is not None and await deps.should_cancel():
            return {"error": CANCELLED, "pending_tool_calls": []}

        # Per-run budget checkpoint (spec 49): stop before performing an over-budget step.
        # Cost uses the prompt/completion split via `cost_for()` so the mid-run gate and
        # the post-run rollup (api/jobs.py) apply the *same* formula (spec 49 §5.2), rather
        # than an averaged single rate.
        usage = state.get("usage", LLMUsage())
        total = state.get("total_tokens", 0)
        cost = cost_for(settings, deps.llm.model, usage.prompt, usage.completion)
        if run_tokens_exceeded(total, settings) or run_cost_exceeded(float(cost), settings):
            return {"error": BUDGET_EXCEEDED, "pending_tool_calls": []}

        messages = _frame_for_llm(state["messages"]) if deps.injection_guard else state["messages"]
        # Deliberate deviation from spec 44 §5.4.1 (which calls for `LLMClient.stream`):
        # we use `complete()` because the full response is needed for `tool_calls`/`usage`
        # and to keep tool flows correct and tests deterministic; the prose is re-chunked
        # into `token` events below. See ADR 0044 §3 for the rationale. True incremental
        # token streaming from the provider is a future refinement.
        try:
            response = await deps.llm.complete(
                messages,
                tools=tool_specs,
                temperature=settings.agent_temperature,
                max_tokens=settings.agent_max_tokens_per_call,
            )
        except LLMError as exc:
            return {"error": str(exc), "pending_tool_calls": []}
        except Exception as exc:  # never crash the graph
            logger.exception("plan node failed")
            return {"error": f"agent error: {exc}", "pending_tool_calls": []}

        # Stream the assistant's prose as `token` events (spec 44).
        if deps.events is not None and response.content:
            for chunk in _chunk(response.content):
                await deps.events.emit("token", text=chunk)

        assistant = LLMMessage(
            role="assistant",
            content=response.content,
            tool_calls=response.tool_calls or None,
        )
        update: dict[str, Any] = {
            "messages": [assistant],
            "iterations": state.get("iterations", 0) + 1,
            "total_tokens": state.get("total_tokens", 0) + response.usage.total,
            "usage": response.usage,  # summed by the state reducer
        }
        if response.tool_calls:
            update["pending_tool_calls"] = response.tool_calls
        else:
            update["pending_tool_calls"] = []
            update["final_response"] = response.content
        return update

    return plan


def make_act(deps: AgentDeps) -> Any:
    registry = deps.tools
    ctx = deps.tool_context

    async def act(state: AgentState) -> dict[str, Any]:
        if deps.should_cancel is not None and await deps.should_cancel():
            return {"error": CANCELLED, "pending_tool_calls": []}

        results: list[LLMMessage] = []
        before = len(ctx.staged_edits) if ctx is not None else 0

        for call in state.get("pending_tool_calls", []):
            if deps.events is not None:
                await deps.events.emit(
                    "tool_call", tool_call_id=call.id, name=call.name, arguments=call.arguments
                )
            if ctx is not None:
                ctx.audit_events.append({"action": "tool_call", "tool_name": call.name})
            tool = registry.get(call.name)
            if tool is None:
                # Capability guard (spec 49): a tool not in the allow-list is never run.
                result = ToolResult.failure("unsupported", f"unknown tool: {call.name}")
                if ctx is not None:
                    ctx.audit_events.append(
                        {
                            "action": "injection_flagged",
                            "tool_name": call.name,
                            "detail": {"reason": "disallowed_tool"},
                            "outcome": "blocked",
                        }
                    )
            elif ctx is None:
                result = ToolResult.failure("internal", "no tool context available")
            else:
                try:
                    parsed = tool.Args.model_validate(call.arguments)
                except ValidationError as exc:
                    result = ToolResult.failure("invalid_args", str(exc))
                else:
                    try:
                        result = await tool.run(parsed, ctx)
                    except Exception as exc:  # only truly unexpected errors reach here
                        logger.exception("tool %s raised", call.name)
                        result = ToolResult.failure("internal", str(exc))
            content = result.model_dump_json()
            if ctx is not None:
                ctx.audit_events.append(
                    {
                        "action": "tool_result",
                        "tool_name": call.name,
                        "outcome": "ok" if result.ok else "error",
                    }
                )
                # Heuristic injection flag on untrusted tool/document content (spec 49).
                if ctx.injection_guard and flag_injection(content):
                    ctx.audit_events.append(
                        {
                            "action": "injection_flagged",
                            "tool_name": call.name,
                            "detail": {"reason": "override_pattern_in_content"},
                        }
                    )
            if deps.events is not None:
                await deps.events.emit(
                    "tool_result",
                    tool_call_id=call.id,
                    name=call.name,
                    ok=result.ok,
                    summary=_result_summary(result),
                )
            results.append(
                LLMMessage(role="tool", tool_call_id=call.id, name=call.name, content=content)
            )

        update: dict[str, Any] = {"messages": results, "pending_tool_calls": []}
        if ctx is not None and len(ctx.staged_edits) > before:
            update["staged_edits"] = ctx.staged_edits[before:]
        return update

    return act


def make_observe(deps: AgentDeps) -> Any:
    async def observe(_state: AgentState) -> dict[str, Any]:
        # Tool results are already appended in `act`; bookkeeping placeholder (spec 41).
        return {}

    return observe


def make_respond(deps: AgentDeps) -> Any:
    async def respond(state: AgentState) -> dict[str, Any]:
        if state.get("final_response") is not None and not state.get("error"):
            # The plan node already appended the final assistant message.
            return {"final_response": state.get("final_response")}

        if state.get("error"):
            err: str = state["error"]  # type: ignore[assignment]
            text = _ERROR_CLOSINGS.get(err, "The run ended early due to an error.")
            return {
                "messages": [LLMMessage(role="assistant", content=text)],
                "final_response": text,
            }

        # Capped without error: reuse the last assistant content if present (do NOT
        # duplicate it into a second row); only synthesize a closing message when the
        # transcript has no usable assistant content (e.g. a tool-only loop).
        last = _last_assistant_content(state.get("messages", []))
        if last is not None:
            return {"final_response": last}
        closing = "I reached my step limit for this turn before finishing."
        return {
            "messages": [LLMMessage(role="assistant", content=closing)],
            "final_response": closing,
        }

    return respond
