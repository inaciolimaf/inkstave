"""The ``project_invites`` table — pending email invitations to a project (spec 33)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InviteRole(enum.StrEnum):
    editor = "editor"
    viewer = "viewer"


class InviteStatus(enum.StrEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    revoked = "revoked"
    expired = "expired"


class ProjectInvite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_invites"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # CITEXT: invitations are matched case-insensitively against the user's email.
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # SHA-256 hex of the opaque bearer token; the raw token is returned only at
    # creation time and never persisted (see docs/adr/0033-collaborators-sharing.md).
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=InviteStatus.pending.value
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("role IN ('editor','viewer')", name="invite_role_valid"),
        CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')",
            name="invite_status_valid",
        ),
        Index("ix_project_invites_project_id_email", "project_id", "email"),
        # At most one pending invite per (project, email).
        Index(
            "uq_invite_one_pending",
            "project_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
