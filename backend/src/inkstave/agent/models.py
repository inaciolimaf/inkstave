"""Persistence models for the AI agent (spec 41): sessions + messages.

Enum-like columns follow the project convention (``String`` + ``CheckConstraint``,
as in memberships) rather than native PG enum types.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentSessionStatus(enum.StrEnum):
    active = "active"
    archived = "archived"


class AgentMessageRole(enum.StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class AgentRunState(enum.StrEnum):
    idle = "idle"
    queued = "queued"
    running = "running"
    cancelling = "cancelling"
    done = "done"
    error = "error"


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_sessions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=AgentSessionStatus.active.value
    )
    model: Mapped[str] = mapped_column(Text, nullable=False)
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    run_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=AgentRunState.idle.value
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','archived')", name="agent_session_status_valid"),
        CheckConstraint(
            "run_state IN ('idle','queued','running','cancelling','done','error')",
            name="agent_session_run_state_valid",
        ),
        Index("ix_agent_sessions_project_id", "project_id"),
        Index("ix_agent_sessions_user_id", "user_id"),
        Index(
            "ix_agent_sessions_project_user_updated",
            "project_id",
            "user_id",
            text("updated_at DESC"),
        ),
    )


class AgentMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('system','user','assistant','tool')", name="agent_message_role_valid"
        ),
        UniqueConstraint("session_id", "seq", name="uq_agent_messages_session_seq"),
        Index("ix_agent_messages_session_id", "session_id"),
    )
