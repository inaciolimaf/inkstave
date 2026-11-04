"""The ``project_memberships`` table — who can access a project and as what (spec 33)."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class MembershipRole(enum.StrEnum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class MembershipStatus(enum.StrEnum):
    active = "active"
    pending = "pending"
    left = "left"


class ProjectMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_memberships"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=MembershipStatus.active.value
    )
    # Set when a share link created or upgraded this membership (spec 116). Cleared when the owner
    # changes the role by hand or the member accepts an e-mail invite.
    via_link_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_share_links.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The role held before a link upgraded the member; null when the link created the membership.
    role_before_link: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # "Suggesting" mode of the member in this project (spec 119): their edits become suggestions.
    suggest_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),
        CheckConstraint("role IN ('owner','editor','viewer')", name="membership_role_valid"),
        CheckConstraint("status IN ('active','pending','left')", name="membership_status_valid"),
        CheckConstraint(
            "role_before_link IS NULL OR role_before_link IN ('viewer','editor')",
            name="membership_role_before_link_valid",
        ),
        Index(
            "ix_project_memberships_via_link_id",
            "via_link_id",
            postgresql_where=text("via_link_id IS NOT NULL"),
        ),
        Index("ix_project_memberships_project_id", "project_id"),
        Index("ix_project_memberships_user_id", "user_id"),
        # "Projects I actively belong to" (spec 109): the listing joins on this partial index.
        Index(
            "ix_project_memberships_user_active",
            "user_id",
            "project_id",
            postgresql_where=text("status = 'active'"),
        ),
        # At most one owner per project (enforced at the DB layer, belt-and-braces
        # with the service-level invariant).
        Index(
            "uq_membership_one_owner",
            "project_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )
