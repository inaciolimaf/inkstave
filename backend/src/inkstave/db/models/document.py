"""The ``documents`` table — text content of a ``doc`` tree entity (spec 13).

A satellite of ``tree_entities`` keyed 1:1 by ``entity_id`` (which *is* the PK).
A single UTF-8 text blob plus an integer optimistic-concurrency ``version``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from inkstave.db.models.project import Project
    from inkstave.db.models.tree_entity import TreeEntity


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    # The doc tree-entity id is the primary key (1:1 satellite).
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tree_entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Denormalised for fast project-scoped queries; kept consistent in the service.
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    entity: Mapped[TreeEntity] = relationship(back_populates="document")
    project: Mapped[Project] = relationship()

    __table_args__ = (
        CheckConstraint("version >= 0", name="version_non_negative"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        Index("ix_documents_project_id", "project_id"),
    )
