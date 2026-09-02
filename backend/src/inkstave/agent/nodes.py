"""Graph node functions: plan / act / observe / respond (spec 41).

These reach the model only through the injected ``LLMClient`` (``deps.llm``) — they
never import the OpenAI SDK. A turn with no tools simply plans then responds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from inkstave.agent.llm.base import LLMError, LLMMessage, LLMResponse, LLMUsage
from inkstave.agent.safety.budget import cost_for, run_cost_exceeded, run_tokens_exceeded
from inkstave.agent.safety.injection import flag_injection, wrap_untrusted
from inkstave.agent.state import AgentState
from inkstave.agent.tools.base import ToolResult

if TYPE_CHECKING:
    from inkstave.agent.api.events import EventSink
    from inkstave.agent.deps import AgentDeps
    from inkstave.agent.llm.base import ToolCall, ToolSpec
    from inkstave.agent.settings import AgentSettings
    from inkstave.agent.tools.base import ToolContext, ToolRegistry

logger = logging.getLogger("inkstave.agent")

# Sentinel error values (spec 44 / 49).
CANCELLED = "cancelled"
BUDGET_EXCEEDED = "budget_exceeded"
# The provider returned a tool call the LLM client could not parse (see openrouter.py).
TOOL_CALL_UNPARSED = "tool_call_unparsed"

# User-facing closing text for a terminal error — the raw sentinel / exception string
# is never persisted into the chat transcript (spec 50 refactor).
_ERROR_CLOSINGS = {
    CANCELLED: "Run cancelled.",
    BUDGET_EXCEEDED: "This run reached its token or cost budget.",
    TOOL_CALL_UNPARSED: (
        "I tried to edit a file but the response could not be read. Please try again, "
        "or ask for a smaller change (one file or section at a time)."
    ),
}

# Shown (and streamed) when the turn is cut off by the iteration/token budget while the
# model still had work queued — so a partial result is not mistaken for a finished one.
_CAPPED_NOTE = (
    "⚠️ I stopped before finishing because this turn reached its size limit, so the "
    "result may be partial. Any edits proposed above are ready to review — ask me to "
    "continue, ideally one file or section at a time."
)


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


def _terminal(error: str) -> dict[str, Any]:
    """A state update that ends the turn with `error` and nothing queued."""
    return {"error": error, "pending_tool_calls": []}


async def _cancelled(deps: AgentDeps) -> bool:
    """True when the run has an attached cancel check and it has fired."""
    return deps.should_cancel is not None and await deps.should_cancel()


async def _emit(events: EventSink | None, event: str, /, **fields: Any) -> None:
    """Emit a stream event when the run is streamed; a no-op otherwise."""
    if events is not None:
        await events.emit(event, **fields)


async def _stream_prose(events: EventSink | None, content: str | None) -> None:
    """Stream the assistant's prose as `token` events (spec 44)."""
    if not content:
        return
    for chunk in _chunk(content):
        await _emit(events, "token", text=chunk)


class _PlanAborted(Exception):
    """The model call failed; `error` is the sentinel to end the turn with."""

    def __init__(self, error: str) -> None:
        super().__init__(error)
        self.error = error


def _budget_exceeded(state: AgentState, settings: AgentSettings, model: str) -> bool:
    """Per-run budget checkpoint (spec 49): stop before an over-budget step.

    Cost uses the prompt/completion split via `cost_for()` so the mid-run gate and
    the post-run rollup (api/jobs.py) apply the *same* formula (spec 49 §5.2),
    rather than an averaged single rate.
    """
    usage = state.get("usage", LLMUsage())
    total = state.get("total_tokens", 0)
    cost = cost_for(settings, model, usage.prompt, usage.completion)
    return run_tokens_exceeded(total, settings) or run_cost_exceeded(float(cost), settings)


async def _complete(
    deps: AgentDeps, messages: list[LLMMessage], tool_specs: list[ToolSpec] | None
) -> LLMResponse:
    """One model call, with every failure mode turned into `_PlanAborted`.

    Deliberate deviation from spec 44 §5.4.1 (which calls for `LLMClient.stream`):
    we use `complete()` because the full response is needed for `tool_calls`/`usage`
    and to keep tool flows correct and tests deterministic; the prose is re-chunked
    into `token` events by the caller. See ADR 0044 §3 for the rationale. True
    incremental token streaming from the provider is a future refinement.
    """
    try:
        return await deps.llm.complete(
            messages,
            tools=tool_specs,
            temperature=deps.settings.agent_temperature,
            max_tokens=deps.settings.agent_max_tokens_per_call,
        )
    except LLMError as exc:
        raise _PlanAborted(str(exc)) from exc
    except Exception as exc:  # never crash the graph
        logger.exception("plan node failed")
        raise _PlanAborted(f"agent error: {exc}") from exc


def _unparsed_tool_call(response: LLMResponse) -> str | None:
    """The sentinel for a tool call the client could not parse, else ``None``.

    The provider signalled a tool call but forced `finish_reason` to "error" with no
    usable calls. Ending the turn as a plain answer would drop the intended edit
    silently, so the caller fails loudly instead (spec 41 §4).
    """
    if not response.tool_calls and response.finish_reason == "error":
        return TOOL_CALL_UNPARSED
    return None


def _plan_update(state: AgentState, response: LLMResponse) -> dict[str, Any]:
    """The state update for a completed plan step."""
    assistant = LLMMessage(
        role="assistant", content=response.content, tool_calls=response.tool_calls or None
    )
    update: dict[str, Any] = {
        "messages": [assistant],
        "iterations": state.get("iterations", 0) + 1,
        "total_tokens": state.get("total_tokens", 0) + response.usage.total,
        "usage": response.usage,  # summed by the state reducer
        "pending_tool_calls": response.tool_calls or [],
    }
    if not response.tool_calls:
        update["final_response"] = response.content
    return update


def make_plan(deps: AgentDeps) -> Any:
    tool_specs = deps.tools.specs() or None

    async def plan(state: AgentState) -> dict[str, Any]:
        if await _cancelled(deps):
            return _terminal(CANCELLED)
        if _budget_exceeded(state, deps.settings, deps.llm.model):
            return _terminal(BUDGET_EXCEEDED)

        messages = _frame_for_llm(state["messages"]) if deps.injection_guard else state["messages"]
        iteration = state.get("iterations", 0) + 1
        logger.info("agent plan: iteration=%d calling LLM (%d messages)", iteration, len(messages))
        try:
            response = await _complete(deps, messages, tool_specs)
        except _PlanAborted as aborted:
            return _terminal(aborted.error)

        logger.info(
            "agent plan: iteration=%d LLM finish=%s tool_calls=%d tokens=%d",
            iteration,
            response.finish_reason,
            len(response.tool_calls or []),
            response.usage.total,
        )
        unparsed = _unparsed_tool_call(response)
        if unparsed is not None:
            return _terminal(unparsed)

        await _stream_prose(deps.events, response.content)
        return _plan_update(state, response)

    return plan


def _audit(ctx: ToolContext | None, event: dict[str, Any]) -> None:
    """Record one audit event when the turn has a tool context."""
    if ctx is not None:
        ctx.audit_events.append(event)


async def _run_tool(registry: ToolRegistry, ctx: ToolContext | None, call: ToolCall) -> ToolResult:
    """Validate and run one requested tool, never raising."""
    tool = registry.get(call.name)
    if tool is None:
        # Capability guard (spec 49): a tool not in the allow-list is never run.
        _audit(
            ctx,
            {
                "action": "injection_flagged",
                "tool_name": call.name,
                "detail": {"reason": "disallowed_tool"},
                "outcome": "blocked",
            },
        )
        return ToolResult.failure("unsupported", f"unknown tool: {call.name}")
    if ctx is None:
        return ToolResult.failure("internal", "no tool context available")
    try:
        parsed = tool.Args.model_validate(call.arguments)
    except ValidationError as exc:
        return ToolResult.failure("invalid_args", str(exc))
    try:
        return await tool.run(parsed, ctx)
    except Exception as exc:  # only truly unexpected errors reach here
        logger.exception("tool %s raised", call.name)
        return ToolResult.failure("internal", str(exc))


def _audit_result(ctx: ToolContext | None, name: str, result: ToolResult, content: str) -> None:
    """Record the tool's outcome, flagging injection-shaped untrusted content."""
    if ctx is None:
        return
    _audit(
        ctx,
        {"action": "tool_result", "tool_name": name, "outcome": "ok" if result.ok else "error"},
    )
    # Heuristic injection flag on untrusted tool/document content (spec 49).
    if ctx.injection_guard and flag_injection(content):
        _audit(
            ctx,
            {
                "action": "injection_flagged",
                "tool_name": name,
                "detail": {"reason": "override_pattern_in_content"},
            },
        )


async def _dispatch_call(
    deps: AgentDeps, registry: ToolRegistry, ctx: ToolContext | None, call: ToolCall
) -> LLMMessage:
    """Run one requested tool, emitting + auditing its call and result."""
    logger.info("agent act: running tool=%s", call.name)
    await _emit(
        deps.events, "tool_call", tool_call_id=call.id, name=call.name, arguments=call.arguments
    )
    _audit(ctx, {"action": "tool_call", "tool_name": call.name})

    result = await _run_tool(registry, ctx, call)
    content = result.model_dump_json()
    _audit_result(ctx, call.name, result, content)

    logger.info("agent act: tool=%s ok=%s → %s", call.name, result.ok, _result_summary(result))
    await _emit(
        deps.events,
        "tool_result",
        tool_call_id=call.id,
        name=call.name,
        ok=result.ok,
        summary=_result_summary(result),
    )
    return LLMMessage(role="tool", tool_call_id=call.id, name=call.name, content=content)


def make_act(deps: AgentDeps) -> Any:
    registry = deps.tools
    ctx = deps.tool_context

    async def act(state: AgentState) -> dict[str, Any]:
        if await _cancelled(deps):
            return _terminal(CANCELLED)

        before = len(ctx.staged_edits) if ctx is not None else 0
        results = [
            await _dispatch_call(deps, registry, ctx, call)
            for call in state.get("pending_tool_calls", [])
        ]

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

        # Capped without error: the iteration/token budget cut the turn off mid-work.
        # Stream a clear early-stop note so a partial result is not mistaken for a
        # finished one, then reuse the last assistant content as the final answer when
        # present — without duplicating it into a second row (spec 50).
        last = _last_assistant_content(state.get("messages", []))
        if deps.events is not None:
            await deps.events.emit("token", text=f"\n\n{_CAPPED_NOTE}" if last else _CAPPED_NOTE)
        if last is not None:
            return {"final_response": last}
        return {
            "messages": [LLMMessage(role="assistant", content=_CAPPED_NOTE)],
            "final_response": _CAPPED_NOTE,
        }

    return respond
