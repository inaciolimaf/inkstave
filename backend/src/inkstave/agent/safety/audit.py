"""Audit logging of agent actions (spec 49). Non-blocking; never crashes a run."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.agent.safety.models import AgentAuditAction, AgentAuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("inkstave.agent.audit")


async def audit(
    db: AsyncSession,
    action: AgentAuditAction,
    *,
    user_id: UUID,
    project_id: UUID | None = None,
    session_id: UUID | None = None,
    run_id: UUID | None = None,
    tool_name: str | None = None,
    tokens_prompt: int | None = None,
    tokens_completion: int | None = None,
    cost_estimate_usd: Decimal | None = None,
    outcome: str = "ok",
    detail: dict[str, Any] | None = None,
) -> None:
    """Write one audit row. The caller must pass redacted detail (no secrets/bodies).

    A failed write is logged and swallowed so a run is never crashed by auditing.
    """
    try:
        db.add(
            AgentAuditLog(
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
                run_id=run_id,
                action=action.value,
                tool_name=tool_name,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                cost_estimate_usd=cost_estimate_usd,
                outcome=outcome,
                detail=detail,
            )
        )
        await db.flush()
    except Exception:
        logger.exception("agent audit write failed (action=%s)", action.value)
