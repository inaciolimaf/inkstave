"""The ``files`` table — binary blob metadata for a ``file`` tree entity (spec 14)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CHAR, BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from inkstave.db.models.project import Project
    from inkstave.db.models.tree_entity import TreeEntity


class File(TimestampMixin, Base):
    __tablename__ = "files"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tree_entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entity: Mapped[TreeEntity] = relationship(back_populates="file")
    project: Mapped[Project] = relationship()

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        Index("ix_files_project_id", "project_id"),
        Index("uq_files_storage_key", "storage_key", unique=True),
    )
