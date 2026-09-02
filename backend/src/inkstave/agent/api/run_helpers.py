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
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.api.events import RedisEventSink
from inkstave.agent.models import AgentRunState
from inkstave.agent.nodes import BUDGET_EXCEEDED, CANCELLED
from inkstave.agent.safety import (
    AgentAuditAction,
    AuditSubject,
    audit,
    check_rate_limit,
    cost_for,
    precheck_day,
    record_usage,
)
from inkstave.observability.metrics import inc_agent_request, inc_agent_tokens

logger = logging.getLogger("inkstave.agent.api")


@dataclass(slots=True)
class RunScope:
    """Who one agent run belongs to, plus the infrastructure it writes through.

    Every helper below used to take these nine values one by one; bundling them
    keeps the signatures within the project's argument budget and makes the audit
    rows impossible to mis-scope.
    """

    db: AsyncSession
    redis: Any
    settings: Any
    sink: RedisEventSink
    user_id: UUID
    project_id: UUID
    session_id: UUID
    run_id: UUID
    now: float

    async def audit(self, action: AgentAuditAction, **fields: Any) -> None:
        """Write one audit row, already scoped to this run."""
        subject = AuditSubject(self.user_id, self.project_id, self.session_id, self.run_id)
        await audit(self.db, action, subject, **fields)


async def _check_rate_limit(scope: RunScope, finalize: Callable[[str], Awaitable[None]]) -> bool:
    """Rate limit (spec 49 AC1). False when the run is blocked."""
    rate = await check_rate_limit(
        scope.redis,
        scope.settings,
        user_id=scope.user_id,
        project_id=scope.project_id,
        now=scope.now,
    )
    if rate.allowed:
        return True
    await scope.sink.emit(
        "error",
        code="agent_rate_limited",
        message="Too many agent runs. Please wait a moment.",
        retry_after=rate.retry_after,
    )
    await scope.audit(
        AgentAuditAction.limit_block, outcome="blocked", detail={"reason": rate.reason}
    )
    inc_agent_request("rate_limited")
    await finalize(AgentRunState.error.value)
    return False


async def _check_day_budget(scope: RunScope, finalize: Callable[[str], Awaitable[None]]) -> bool:
    """Per-day budget pre-check (spec 49 AC2). False when the run is blocked."""
    budget = await precheck_day(
        scope.redis,
        scope.settings,
        user_id=scope.user_id,
        project_id=scope.project_id,
        now=scope.now,
    )
    if budget.allowed:
        return True
    await scope.sink.emit(
        "error", code="agent_budget_exceeded", message="Daily usage budget exhausted."
    )
    await scope.audit(
        AgentAuditAction.budget_block,
        outcome="blocked",
        detail={"reason": budget.reason, "phase": "preflight"},
    )
    await finalize(AgentRunState.error.value)
    return False


async def precheck_run(scope: RunScope, finalize: Callable[[str], Awaitable[None]]) -> bool:
    """Run rate-limit then per-day budget pre-checks (spec 49 AC1/AC2).

    Returns ``True`` when the run may proceed. On a block, the failing check has
    already emitted the terminal error event, written the audit row and finalized
    the session to ``error``.
    """
    return await _check_rate_limit(scope, finalize) and await _check_day_budget(scope, finalize)


async def _audit_tool_events(scope: RunScope, events: list[dict[str, Any]]) -> None:
    """Persist the run's tool audit trail, one row per recorded event."""
    for event in events:
        tool_name = event.get("tool_name")
        detail = event.get("detail")
        await scope.audit(
            AgentAuditAction(str(event["action"])),
            tool_name=tool_name if isinstance(tool_name, str) else None,
            outcome=str(event.get("outcome", "ok")),
            detail=detail if isinstance(detail, dict) else None,
        )


async def _announce_diffs(scope: RunScope, diffs: list[Any]) -> None:
    """Stream + audit every diff the run proposed."""
    for diff in diffs:
        await scope.sink.emit(
            "diff_proposed",
            diff_id=str(diff.id),
            doc_id=str(diff.doc_id),
            path=diff.path,
            stats=diff.stats,
        )
        await scope.audit(
            AgentAuditAction.proposal_created,
            detail={
                "diff_id": str(diff.id),
                "path": diff.path,
                "hunks": diff.stats.get("hunk_count"),
            },
        )


async def persist_results(scope: RunScope, *, result: Any, model: str) -> Decimal:
    """Persist audit events + proposed diffs, record usage, emit token metrics.

    Returns the estimated run cost (used later for the ``run_stop`` audit row).
    """
    await _audit_tool_events(scope, result.audit_events)
    await _announce_diffs(scope, result.proposed_diffs)

    cost = cost_for(scope.settings, model, result.usage.prompt, result.usage.completion)
    await record_usage(
        scope.redis,
        user_id=scope.user_id,
        project_id=scope.project_id,
        now=scope.now,
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


async def audit_budget_block_midrun(scope: RunScope) -> None:
    """Write the mid-run budget-block audit row (spec 49)."""
    await scope.audit(AgentAuditAction.budget_block, outcome="blocked", detail={"phase": "midrun"})
