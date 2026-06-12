"""The ``compile_outputs`` table — per-artifact storage metadata (spec 23)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, UUIDPrimaryKeyMixin


class OutputKind(enum.StrEnum):
    PDF = "pdf"
    LOG = "log"
    SYNCTEX = "synctex"
    AUX = "aux"
    OTHER = "other"


class CompileOutput(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "compile_outputs"

    compile_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("compiles.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    rel_path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    etag: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('pdf','log','synctex','aux','other')", name="compile_output_kind_valid"
        ),
        UniqueConstraint("compile_id", "name", name="uq_compile_output_name"),
        Index("ix_compile_outputs_compile_id", "compile_id"),
        Index("ix_compile_outputs_project_created", "project_id", "created_at"),
    )
