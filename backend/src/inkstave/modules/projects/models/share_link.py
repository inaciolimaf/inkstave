"""The ``project_share_links`` table — view and edit links for a project (spec 116)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ShareLinkRole(enum.StrEnum):
    viewer = "viewer"
    editor = "editor"


class ProjectShareLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_share_links"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # SHA-256 hex of the opaque token (``hash_token``); the raw token is returned once, at creation.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('viewer','editor')", name="share_link_role_valid"),
        # At most one active link per project and role.
        Index(
            "uq_share_link_one_active",
            "project_id",
            "role",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
