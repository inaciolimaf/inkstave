"""CRDT persistence tables: per-document state snapshot + append-only log (spec 28).

``crdt_document_state`` is 1:1 with a spec-13 ``documents`` row (keyed by the doc
tree-entity id). ``crdt_update`` is the append-only log of binary Yjs updates
between snapshots, replayed in ``id`` order on load and truncated on compaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, LargeBinary, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base


class CrdtDocumentState(Base):
    __tablename__ = "crdt_document_state"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state_vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    text_synced_seq: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class CrdtUpdate(Base):
    __tablename__ = "crdt_update"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.entity_id", ondelete="CASCADE"),
        nullable=False,
    )
    update: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (Index("ix_crdt_update_document_id_id", "document_id", "id"),)
