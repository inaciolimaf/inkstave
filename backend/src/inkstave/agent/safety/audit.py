"""Audit logging of agent actions (spec 49). Non-blocking; never crashes a run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.agent.safety.models import AgentAuditAction, AgentAuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("inkstave.agent.audit")


@dataclass(slots=True)
class AuditSubject:
    """Who an audit row is about; only the user is always known."""

    user_id: UUID
    project_id: UUID | None = None
    session_id: UUID | None = None
    run_id: UUID | None = None


@dataclass(slots=True)
class AuditUsage:
    """Token + cost figures, recorded on the rows that have them."""

    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    cost_estimate_usd: Decimal | None = None


async def audit(
    db: AsyncSession,
    action: AgentAuditAction,
    subject: AuditSubject,
    *,
    tool_name: str | None = None,
    usage: AuditUsage | None = None,
    outcome: str = "ok",
    detail: dict[str, Any] | None = None,
) -> None:
    """Write one audit row. The caller must pass redacted detail (no secrets/bodies).

    A failed write is logged and swallowed so a run is never crashed by auditing.
    """
    counts = usage or AuditUsage()
    try:
        db.add(
            AgentAuditLog(
                user_id=subject.user_id,
                project_id=subject.project_id,
                session_id=subject.session_id,
                run_id=subject.run_id,
                action=action.value,
                tool_name=tool_name,
                tokens_prompt=counts.tokens_prompt,
                tokens_completion=counts.tokens_completion,
                cost_estimate_usd=counts.cost_estimate_usd,
                outcome=outcome,
                detail=detail,
            )
        )
        await db.flush()
    except Exception:
        logger.exception("agent audit write failed (action=%s)", action.value)
