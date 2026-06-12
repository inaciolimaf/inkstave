"""Agent audit-log model (spec 49)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, UUIDPrimaryKeyMixin


class AgentAuditAction(enum.StrEnum):
    run_start = "run_start"
    run_stop = "run_stop"
    tool_call = "tool_call"
    tool_result = "tool_result"
    proposal_created = "proposal_created"
    apply_recorded = "apply_recorded"
    limit_block = "limit_block"
    budget_block = "budget_block"
    injection_flagged = "injection_flagged"
    error = "error"


_ACTIONS = ",".join(f"'{a.value}'" for a in AgentAuditAction)


class AgentAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_audit_log"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_prompt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_completion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, server_default="ok")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(f"action IN ({_ACTIONS})", name="agent_audit_action_valid"),
        Index("ix_agent_audit_user_created", "user_id", "created_at"),
        Index("ix_agent_audit_project_created", "project_id", "created_at"),
        Index("ix_agent_audit_run", "run_id"),
    )
