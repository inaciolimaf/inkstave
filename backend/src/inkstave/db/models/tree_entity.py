"""The ``tree_entities`` table — a project's file tree as an adjacency list.

Folders, docs and files share one self-referencing table (see
docs/adr/0012-file-tree-model.md). Document text (13) and binary blobs (14)
attach to rows here via satellite tables.
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from inkstave.db.models.document import Document
    from inkstave.db.models.file import File
    from inkstave.db.models.project import Project


class TreeEntityType(enum.StrEnum):
    folder = "folder"
    doc = "doc"
    file = "file"


class TreeEntity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tree_entities"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tree_entities.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[TreeEntityType] = mapped_column(
        Enum(TreeEntityType, name="tree_entity_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_root: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    project: Mapped[Project] = relationship(back_populates="tree_entities")
    parent: Mapped[TreeEntity | None] = relationship(
        back_populates="children", remote_side="TreeEntity.id"
    )
    children: Mapped[list[TreeEntity]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    document: Mapped[Document | None] = relationship(
        back_populates="entity",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    file: Mapped[File | None] = relationship(
        back_populates="entity",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Only folders may have an empty name (the root's name is "").
        CheckConstraint("type = 'folder' OR name <> ''", name="name_not_empty_unless_folder"),
        # The root must be a folder.
        CheckConstraint("NOT is_root OR type = 'folder'", name="root_is_folder"),
        # Exactly the root has a NULL parent.
        CheckConstraint("is_root = (parent_id IS NULL)", name="root_has_no_parent"),
        Index("ix_tree_project_id", "project_id"),
        Index("ix_tree_parent_id", "parent_id"),
        # Per-folder unique name, case-insensitive (NULL parent of the single
        # root is naturally exempt).
        Index("uq_tree_sibling_name", "parent_id", text("lower(name)"), unique=True),
        # At most one root folder per project.
        Index(
            "uq_tree_one_root_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("is_root"),
        ),
    )
