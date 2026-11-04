"""The comment tables: ``comment_threads`` and ``comment_messages`` (spec 118).

A thread anchors to a range of a document by two Yjs relative positions, stored opaque (ADR 0118).
The server never decodes them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, UUIDPrimaryKeyMixin

# Longest encoded anchor, in bytes, and the longest quote kept for the panel. The check constraint repeats
# the anchor limit.
ANCHOR_MAX_BYTES = 256
QUOTE_MAX_CHARS = 500
# A comment message, in characters, as the chat sets it.
COMMENT_BODY_MAX_LENGTH = 4000


class CommentThread(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comment_threads"
    __mapper_args__ = {"eager_defaults": True}

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tree_entities.id", ondelete="CASCADE"), nullable=False
    )
    anchor_start: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    anchor_end: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            f"octet_length(anchor_start) BETWEEN 1 AND {ANCHOR_MAX_BYTES}", name="anchor_start_size"
        ),
        CheckConstraint(f"octet_length(anchor_end) BETWEEN 1 AND {ANCHOR_MAX_BYTES}", name="anchor_end_size"),
        Index("ix_comment_threads_project_document", "project_id", "document_id"),
        Index(
            "ix_comment_threads_open",
            "project_id",
            "document_id",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )


class CommentMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comment_messages"
    __mapper_args__ = {"eager_defaults": True}

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("comment_threads.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Ids the author mentioned, validated as active members when written.
    mentions: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft delete: the message keeps its place and shows "Message deleted".
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {COMMENT_BODY_MAX_LENGTH}", name="body_length"),
        Index("ix_comment_messages_thread_created", "thread_id", "created_at", "id"),
    )
