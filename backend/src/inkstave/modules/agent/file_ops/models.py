"""ProposedFileOp: a create, delete or move the agent proposed and the user decides."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProposedFileOpStatus(enum.StrEnum):
    proposed = "proposed"
    applied = "applied"
    rejected = "rejected"
    superseded = "superseded"


class ProposedFileOp(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proposed_file_ops"

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
    # Null for a create, and once the target is gone: the row outlives what it deleted.
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tree_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    new_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_paths: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ProposedFileOpStatus.proposed.value
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("kind IN ('create','delete','move')", name="proposed_file_op_kind_valid"),
        CheckConstraint(
            "status IN ('proposed','applied','rejected','superseded')", name="proposed_file_op_status_valid"
        ),
        Index("ix_proposed_file_ops_session_created", "session_id", "created_at"),
    )
