"""Helpers extracted from ``run_agent_turn`` (spec 44/49).

Pure structural split of :mod:`inkstave.agent.api.jobs`: the safety pre-checks,
result persistence (audit events, proposed diffs, usage/metrics) and the
terminal-event selection live here so the orchestration in ``jobs.py`` stays
readable. Behaviour and signatures are unchanged — every function is called
exactly where its block used to run inline.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.api.events import RedisEventSink
from inkstave.agent.models import AgentRunState
from inkstave.agent.nodes import BUDGET_EXCEEDED, CANCELLED
from inkstave.agent.safety import (
    AgentAuditAction,
    audit,
    check_rate_limit,
    cost_for,
    precheck_day,
    record_usage,
)
from inkstave.observability.metrics import inc_agent_request, inc_agent_tokens

logger = logging.getLogger("inkstave.agent.api")


async def precheck_run(
    *,
    db: AsyncSession,
    redis: Any,
    settings: Any,
    sink: RedisEventSink,
    user_id: UUID,
    project_id: UUID,
    sid: UUID,
    run_uuid: UUID,
    now: float,
    finalize: Callable[[str], Awaitable[None]],
) -> bool:
    """Run rate-limit then per-day budget pre-checks (spec 49 AC1/AC2).

    Returns ``True`` when the run may proceed. On a block, emits the terminal
    error event, writes the audit row, finalizes the session to ``error`` and
    returns ``False`` — exactly as the inline code did.
    """
    # 1. Rate limit (spec 49 AC1).
    rate = await check_rate_limit(redis, settings, user_id=user_id, project_id=project_id, now=now)
    if not rate.allowed:
        await sink.emit(
            "error",
            code="agent_rate_limited",
            message="Too many agent runs. Please wait a moment.",
            retry_after=rate.retry_after,
        )
        await audit(
            db,
            AgentAuditAction.limit_block,
            user_id=user_id,
            project_id=project_id,
            session_id=sid,
            run_id=run_uuid,
            outcome="blocked",
            detail={"reason": rate.reason},
        )
        inc_agent_request("rate_limited")
        await finalize(AgentRunState.error.value)
        return False

    # 2. Per-day budget pre-check (spec 49 AC2).
    budget = await precheck_day(redis, settings, user_id=user_id, project_id=project_id, now=now)
    if not budget.allowed:
        await sink.emit(
            "error", code="agent_budget_exceeded", message="Daily usage budget exhausted."
        )
        await audit(
            db,
            AgentAuditAction.budget_block,
            user_id=user_id,
            project_id=project_id,
            session_id=sid,
            run_id=run_uuid,
            outcome="blocked",
            detail={"reason": budget.reason, "phase": "preflight"},
        )
        await finalize(AgentRunState.error.value)
        return False

    return True


async def persist_results(
    *,
    db: AsyncSession,
    redis: Any,
    settings: Any,
    sink: RedisEventSink,
    result: Any,
    model: str,
    user_id: UUID,
    project_id: UUID,
    sid: UUID,
    run_uuid: UUID,
    now: float,
) -> Decimal:
    """Persist audit events + proposed diffs, record usage, emit token metrics.

    Returns the estimated run cost (used later for the ``run_stop`` audit row).
    """
    for event in result.audit_events:
        tool_name = event.get("tool_name")
        detail = event.get("detail")
        await audit(
            db,
            AgentAuditAction(str(event["action"])),
            user_id=user_id,
            project_id=project_id,
            session_id=sid,
            run_id=run_uuid,
            tool_name=tool_name if isinstance(tool_name, str) else None,
            outcome=str(event.get("outcome", "ok")),
            detail=detail if isinstance(detail, dict) else None,
        )

    for diff in result.proposed_diffs:
        await sink.emit(
            "diff_proposed",
            diff_id=str(diff.id),
            doc_id=str(diff.doc_id),
            path=diff.path,
            stats=diff.stats,
        )
        await audit(
            db,
            AgentAuditAction.proposal_created,
            user_id=user_id,
            project_id=project_id,
            session_id=sid,
            run_id=run_uuid,
            detail={
                "diff_id": str(diff.id),
                "path": diff.path,
                "hunks": diff.stats.get("hunk_count"),
            },
        )

    cost = cost_for(settings, model, result.usage.prompt, result.usage.completion)
    await record_usage(
        redis,
        user_id=user_id,
        project_id=project_id,
        now=now,
        tokens=result.usage.total,
        cost=cost,
    )
    # Observability (spec 51): token + run-status metrics.
    inc_agent_tokens("prompt", model, result.usage.prompt)
    inc_agent_tokens("completion", model, result.usage.completion)
    return cost


async def emit_terminal(
    *,
    sink: RedisEventSink,
    result: Any,
    run_id: str,
) -> str:
    """Emit the terminal SSE event and return the final ``AgentRunState`` value."""
    if result.error == BUDGET_EXCEEDED:
        await sink.emit(
            "error",
            code="agent_budget_exceeded",
            message="This run reached its token or cost budget.",
        )
        return AgentRunState.error.value
    if result.error == CANCELLED:
        await sink.emit("error", code="cancelled", message="Run cancelled.")
        return AgentRunState.error.value
    if result.error:
        # Never forward the raw internal/LLM error string to the client.
        logger.warning("agent run %s ended with error: %s", run_id, result.error)
        await sink.emit("error", code="internal", message="The agent run failed.")
        return AgentRunState.error.value
    await sink.emit(
        "done",
        usage=result.usage.model_dump(),
        iterations=result.iterations,
        final_text=result.final_response,
    )
    return AgentRunState.done.value


async def audit_budget_block_midrun(
    *,
    db: AsyncSession,
    user_id: UUID,
    project_id: UUID,
    sid: UUID,
    run_uuid: UUID,
) -> None:
    """Write the mid-run budget-block audit row (spec 49)."""
    await audit(
        db,
        AgentAuditAction.budget_block,
        user_id=user_id,
        project_id=project_id,
        session_id=sid,
        run_id=run_uuid,
        outcome="blocked",
        detail={"phase": "midrun"},
    )
