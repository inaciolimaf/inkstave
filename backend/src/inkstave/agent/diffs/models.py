"""ProposedDiff persistence model (spec 43)."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProposedDiffStatus(enum.StrEnum):
    proposed = "proposed"
    applied = "applied"
    partially_applied = "partially_applied"
    rejected = "rejected"
    stale = "stale"
    superseded = "superseded"


_STATUS_VALUES = "'proposed','applied','partially_applied','rejected','stale','superseded'"


class ProposedDiff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposed_diffs"

    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    base_version: Mapped[str] = mapped_column(Text, nullable=False)
    base_hash: Mapped[str] = mapped_column(Text, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    hunks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ProposedDiffStatus.proposed.value
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="proposed_diff_status_valid"),
        Index("ix_proposed_diffs_session_created", "session_id", "created_at"),
        Index("ix_proposed_diffs_project_status", "project_id", "status"),
        Index("ix_proposed_diffs_doc", "doc_id"),
    )
