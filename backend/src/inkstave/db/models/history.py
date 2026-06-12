"""Version-history capture tables (spec 36).

A document's history is stored as **chunks**: each chunk is a base snapshot plus
the ordered incremental updates captured after it, so any version is rebuilt by
replaying updates onto the chunk's base. ``doc_id`` references ``documents.entity_id``
(the doc's tree-entity id, which is the documents PK).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HistoryChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "history_chunks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    start_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    base_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Exactly one of base_snapshot / base_snapshot_blob_key is non-NULL (§5.1.3).
    base_snapshot: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    base_snapshot_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_snapshot_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sealed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index("ix_history_chunks_doc_version", "doc_id", "start_version"),
        Index("ix_history_chunks_project", "project_id", "created_at"),
        # At most one open (un-sealed) chunk per document.
        Index(
            "uq_history_chunks_open",
            "doc_id",
            unique=True,
            postgresql_where=text("sealed = false"),
        ),
        # Exactly one of base_snapshot / base_snapshot_blob_key is non-NULL (spec 40).
        CheckConstraint(
            "(base_snapshot IS NULL) <> (base_snapshot_blob_key IS NULL)",
            name="ck_history_chunks_base_xor",
        ),
    )


class HistoryUpdate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "history_updates"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("history_chunks.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Monotonic per doc; the document's history version after this update applies.
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False)
    op_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        Index("uq_history_updates_doc_version", "doc_id", "version", unique=True),
        Index("ix_history_updates_chunk", "chunk_id", "version"),
        Index("ix_history_updates_project_ts", "project_id", "timestamp"),
        # Exactly one of payload / payload_blob_key is non-NULL (spec 40).
        CheckConstraint(
            "(payload IS NULL) <> (payload_blob_key IS NULL)",
            name="ck_history_updates_payload_xor",
        ),
    )


class HistoryLabel(UUIDPrimaryKeyMixin, Base):
    """A named checkpoint on a (doc, version) or a project-level version marker (spec 37)."""

    __tablename__ = "history_labels"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # NULL for a project-level label (its `payload` then holds the {doc_id: version} map).
    doc_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Project-level labels record each document's current version at creation time.
    payload: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_history_labels_doc", "doc_id", "version"),
        Index("ix_history_labels_project", "project_id", "created_at"),
        Index(
            "uq_history_labels_doc_name",
            "doc_id",
            "name",
            unique=True,
            postgresql_where=text("doc_id IS NOT NULL"),
        ),
        Index(
            "uq_history_labels_project_name",
            "project_id",
            "name",
            unique=True,
            postgresql_where=text("doc_id IS NULL"),
        ),
    )
