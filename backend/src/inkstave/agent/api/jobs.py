"""The ``run_agent_turn`` ARQ job (spec 44, safety-enforced in spec 49).

Run-start order: rate-limit → per-day budget pre-check → run the graph (with a
per-run budget checkpoint, injection framing, and the tool capability guard) →
audit throughout. Never makes network calls except through the injected ``LLMClient``;
all exceptions become a terminal ``error`` event — the worker never crashes.

The result-persistence, pre-check and terminal-event helpers live in
:mod:`inkstave.agent.api.run_helpers`; the optional audit-cleanup cron lives in
:mod:`inkstave.agent.api.cleanup` and is re-exported here so the worker
registration path is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from uuid import UUID, uuid4

from inkstave.agent.api.cleanup import agent_audit_cleanup
from inkstave.agent.api.events import RedisEventSink, is_cancel_requested
from inkstave.agent.api.run_helpers import (
    RunScope,
    audit_budget_block_midrun,
    emit_terminal,
    persist_results,
    precheck_run,
)
from inkstave.agent.deps import AgentDeps
from inkstave.agent.models import AgentRunState, AgentSession
from inkstave.agent.nodes import BUDGET_EXCEEDED
from inkstave.agent.runner import run_turn
from inkstave.agent.safety import (
    AgentAuditAction,
    AuditUsage,
    acquire_run,
    avg_rate_per_1k,
    release_run,
)
from inkstave.agent.tools import default_registry
from inkstave.observability.context import bind_context, clear_context
from inkstave.observability.metrics import inc_agent_request

__all__ = ["run_agent_turn", "agent_audit_cleanup"]

logger = logging.getLogger("inkstave.agent.api")


async def run_agent_turn(
    ctx: dict[str, Any],
    *,
    session_id: str,
    run_id: str,
    user_message: str,
    request_id: str | None = None,
) -> None:
    """Bind job correlation context, run the turn, and always clear it (spec 51/55).

    The ``finally`` guarantees the contextvars reset on every path — early return,
    exception, or normal completion — so nothing leaks into the next job the
    worker picks up. ``request_id`` chains back to the enqueuing HTTP request.
    """
    rid = request_id or str(ctx.get("request_id") or uuid4().hex)
    tokens = bind_context(job_id=run_id, job_name="run_agent_turn", request_id=rid, trace_id=rid)
    try:
        await _run_agent_turn(ctx, session_id=session_id, run_id=run_id, user_message=user_message)
    finally:
        clear_context(tokens)


def _resolve_llm(ctx: dict[str, Any], settings: Any) -> Any:
    """The injected LLM client, or the real OpenRouter one (imported lazily)."""
    llm = ctx.get("llm_client")
    if llm is not None:
        return llm
    from inkstave.agent.llm.openrouter import OpenRouterLLMClient

    return OpenRouterLLMClient(settings)


def _build_deps(scope: RunScope, llm: Any, run_id: str) -> AgentDeps:
    """The graph's injected dependencies for this run."""

    async def should_cancel() -> bool:
        return await is_cancel_requested(scope.redis, run_id)

    settings = scope.settings
    return AgentDeps(
        llm=llm,
        settings=settings,
        tools=default_registry(),
        events=scope.sink,
        should_cancel=should_cancel,
        injection_guard=settings.agent_injection_guard == "on",
        run_token_budget=settings.agent_max_tokens_per_run,
        run_cost_budget_usd=settings.agent_max_cost_per_run_usd,
        cost_per_1k=avg_rate_per_1k(settings, llm.model),
    )


async def _settle_error(scope: RunScope, *, code: str, message: str) -> None:
    """Roll back, stream a terminal error, and free the session (no wedged run)."""
    await scope.db.rollback()
    inc_agent_request("error")
    await scope.sink.emit("error", code=code, message=message)
    failed = await scope.db.get(AgentSession, scope.session_id)
    if failed is not None:
        failed.run_state = AgentRunState.error.value
        failed.active_run_id = None
    await scope.audit(AgentAuditAction.error, outcome="error")
    await scope.db.commit()


def _log_done(run_id: str, final_state: str, result: Any) -> None:
    """One summary line per finished run (the SSE stream carries the detail)."""
    logger.info(
        "agent run %s done: state=%s iterations=%d diffs=%d tokens=%d error=%s",
        run_id,
        final_state,
        result.iterations,
        len(result.proposed_diffs),
        result.usage.total,
        result.error or "-",
    )


async def _execute_turn(
    scope: RunScope, session: AgentSession, *, run_id: str, user_message: str, llm: Any
) -> None:
    """Run the graph and settle every terminal record for a run that started."""
    session.run_state = AgentRunState.running.value
    await scope.db.commit()
    await scope.audit(AgentAuditAction.run_start)
    await scope.db.commit()

    deps = _build_deps(scope, llm, run_id)
    result = await run_turn(session=session, user_message=user_message, deps=deps, db=scope.db)

    cost = await persist_results(scope, result=result, model=llm.model)
    final_state = await emit_terminal(sink=scope.sink, result=result, run_id=run_id)
    _log_done(run_id, final_state, result)
    if result.error == BUDGET_EXCEEDED:
        await audit_budget_block_midrun(scope)

    done = final_state == AgentRunState.done.value
    await scope.audit(
        AgentAuditAction.run_stop,
        usage=AuditUsage(
            tokens_prompt=result.usage.prompt,
            tokens_completion=result.usage.completion,
            cost_estimate_usd=cost,
        ),
        outcome="ok" if done else "blocked",
    )
    inc_agent_request("success" if done else "error")
    session.run_state = final_state
    session.active_run_id = None
    await scope.db.commit()


async def _run_scoped(
    scope: RunScope, session: AgentSession, *, run_id: str, user_message: str, llm: Any
) -> None:
    """Pre-checks, concurrency slot, and the error settling around one turn."""

    async def finalize(state_value: str) -> None:
        session.run_state = state_value
        session.active_run_id = None
        await scope.db.commit()

    if not await precheck_run(scope, finalize):
        return

    # acquire_run lives inside the try so any failure during setup still releases
    # the concurrency slot and streams a terminal error (no stuck "running" run).
    await acquire_run(
        scope.redis, user_id=scope.user_id, project_id=scope.project_id, now=scope.now
    )
    try:
        await _execute_turn(scope, session, run_id=run_id, user_message=user_message, llm=llm)
    except asyncio.CancelledError:
        # ARQ enforces the per-job timeout (agent_job_timeout_s) by cancelling the
        # task with CancelledError — a BaseException, so the ``except Exception``
        # below never sees it. Without this branch the session would wedge in
        # ``running`` with no terminal event and the diffs would never commit.
        # Settle it as a ``timeout`` error (shielded so the cleanup survives the
        # cancellation), then re-raise so the task still terminates as cancelled.
        logger.warning("run_agent_turn timed out / cancelled for run %s", run_id)
        settle = _settle_error(scope, code="timeout", message="The agent run timed out.")
        await asyncio.shield(settle)
        raise
    except Exception:
        logger.exception("run_agent_turn failed for run %s", run_id)
        await _settle_error(scope, code="internal", message="The agent run failed.")
    finally:
        await release_run(scope.redis, user_id=scope.user_id)


async def _run_agent_turn(
    ctx: dict[str, Any], *, session_id: str, run_id: str, user_message: str
) -> None:
    # The shared ARQ ctx carries the compile ``Settings`` under "settings" (compile/
    # history/mailer jobs need it); the agent turn needs ``AgentSettings``. The
    # worker provides those under "agent_settings"; tests that hand-build a ctx put
    # an ``AgentSettings`` straight into "settings", so fall back to that.
    settings = ctx.get("agent_settings") or ctx["settings"]
    redis = ctx["redis"]
    sink = ctx.get("event_sink") or RedisEventSink(redis, run_id, settings.agent_run_ttl_s)
    llm = _resolve_llm(ctx, settings)
    sid = UUID(session_id)

    async with ctx["session_factory"]() as db:
        session = await db.get(AgentSession, sid)
        if session is None:
            await sink.emit("error", code="not_found", message="session not found")
            return
        scope = RunScope(
            db=db,
            redis=redis,
            settings=settings,
            sink=sink,
            user_id=session.user_id,
            project_id=session.project_id,
            session_id=sid,
            run_id=UUID(run_id),
            now=ctx.get("clock", time.time)(),
        )
        logger.info(
            "agent run %s start: session=%s project=%s msg_chars=%d",
            run_id,
            session_id,
            scope.project_id,
            len(user_message),
        )
        await _run_scoped(scope, session, run_id=run_id, user_message=user_message, llm=llm)
