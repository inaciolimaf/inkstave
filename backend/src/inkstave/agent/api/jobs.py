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

import logging
import time
from typing import Any
from uuid import UUID, uuid4

from inkstave.agent.api.cleanup import agent_audit_cleanup
from inkstave.agent.api.events import RedisEventSink, is_cancel_requested
from inkstave.agent.api.run_helpers import (
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
    acquire_run,
    audit,
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


async def _run_agent_turn(
    ctx: dict[str, Any], *, session_id: str, run_id: str, user_message: str
) -> None:
    # The shared ARQ ctx carries the compile ``Settings`` under "settings" (compile/
    # history/mailer jobs need it); the agent turn needs ``AgentSettings``. The
    # worker provides those under "agent_settings"; tests that hand-build a ctx put
    # an ``AgentSettings`` straight into "settings", so fall back to that.
    settings = ctx.get("agent_settings") or ctx["settings"]
    session_factory = ctx["session_factory"]
    redis = ctx["redis"]
    clock = ctx.get("clock", time.time)
    sink = ctx.get("event_sink") or RedisEventSink(redis, run_id, settings.agent_run_ttl_s)

    llm = ctx.get("llm_client")
    if llm is None:
        from inkstave.agent.llm.openrouter import OpenRouterLLMClient

        llm = OpenRouterLLMClient(settings)

    sid = UUID(session_id)
    run_uuid = UUID(run_id)

    async with session_factory() as db:
        session = await db.get(AgentSession, sid)
        if session is None:
            await sink.emit("error", code="not_found", message="session not found")
            return
        user_id = session.user_id
        project_id = session.project_id
        now = clock()

        async def finalize(state_value: str) -> None:
            session.run_state = state_value
            session.active_run_id = None
            await db.commit()

        if not await precheck_run(
            db=db,
            redis=redis,
            settings=settings,
            sink=sink,
            user_id=user_id,
            project_id=project_id,
            sid=sid,
            run_uuid=run_uuid,
            now=now,
            finalize=finalize,
        ):
            return

        async def should_cancel() -> bool:
            return await is_cancel_requested(redis, run_id)

        # acquire_run lives inside the try so any failure during setup still releases
        # the concurrency slot and streams a terminal error (no stuck "running" run).
        await acquire_run(redis, user_id=user_id, project_id=project_id, now=now)
        try:
            session.run_state = AgentRunState.running.value
            await db.commit()
            await audit(
                db,
                AgentAuditAction.run_start,
                user_id=user_id,
                project_id=project_id,
                session_id=sid,
                run_id=run_uuid,
            )
            await db.commit()

            deps = AgentDeps(
                llm=llm,
                settings=settings,
                tools=default_registry(),
                events=sink,
                should_cancel=should_cancel,
                injection_guard=settings.agent_injection_guard == "on",
                run_token_budget=settings.agent_max_tokens_per_run,
                run_cost_budget_usd=settings.agent_max_cost_per_run_usd,
                cost_per_1k=avg_rate_per_1k(settings, llm.model),
            )
            result = await run_turn(session=session, user_message=user_message, deps=deps, db=db)

            cost = await persist_results(
                db=db,
                redis=redis,
                settings=settings,
                sink=sink,
                result=result,
                model=llm.model,
                user_id=user_id,
                project_id=project_id,
                sid=sid,
                run_uuid=run_uuid,
                now=now,
            )

            final_state = await emit_terminal(sink=sink, result=result, run_id=run_id)
            if result.error == BUDGET_EXCEEDED:
                await audit_budget_block_midrun(
                    db=db,
                    user_id=user_id,
                    project_id=project_id,
                    sid=sid,
                    run_uuid=run_uuid,
                )

            await audit(
                db,
                AgentAuditAction.run_stop,
                user_id=user_id,
                project_id=project_id,
                session_id=sid,
                run_id=run_uuid,
                tokens_prompt=result.usage.prompt,
                tokens_completion=result.usage.completion,
                cost_estimate_usd=cost,
                outcome="ok" if final_state == AgentRunState.done.value else "blocked",
            )
            inc_agent_request("success" if final_state == AgentRunState.done.value else "error")
            session.run_state = final_state
            session.active_run_id = None
            await db.commit()
        except Exception:
            logger.exception("run_agent_turn failed for run %s", run_id)
            await db.rollback()
            inc_agent_request("error")
            await sink.emit("error", code="internal", message="The agent run failed.")
            session = await db.get(AgentSession, sid)
            if session is not None:
                session.run_state = AgentRunState.error.value
                session.active_run_id = None
            await audit(
                db,
                AgentAuditAction.error,
                user_id=user_id,
                project_id=project_id,
                session_id=sid,
                run_id=run_uuid,
                outcome="error",
            )
            await db.commit()
        finally:
            await release_run(redis, user_id=user_id)
