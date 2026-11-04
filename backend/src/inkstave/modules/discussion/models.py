"""The project chat tables: ``project_chat_messages`` and ``project_chat_reads`` (spec 117)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, UUIDPrimaryKeyMixin

# Longest message the chat accepts, in characters. The check constraint repeats it.
CHAT_BODY_MAX_LENGTH = 4000


class ProjectChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_chat_messages"
    # The server default for created_at comes back via RETURNING: a lazy refresh would fail under async.
    __mapper_args__ = {"eager_defaults": True}

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # The author may leave the project or the service; the message stays.
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Soft delete: the row stays so the timeline shows "Message deleted" for everyone.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {CHAT_BODY_MAX_LENGTH}", name="body_length"),
        Index("ix_project_chat_messages_project_created", "project_id", text("created_at DESC"), "id"),
    )


class ProjectChatRead(Base):
    """Per user and project: when the chat was last opened. Drives the unread count."""

    __tablename__ = "project_chat_reads"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
