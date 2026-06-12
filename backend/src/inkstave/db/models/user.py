"""The ``users`` table — the canonical account identity (spec 06)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from inkstave.db.models.project import Project


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Partial indexes for the email-change lookups (spec 59) — only the few rows
    # with a pending change are indexed.
    __table_args__ = (
        Index(
            "ix_users_email_change_token_hash",
            "email_change_token_hash",
            postgresql_where=text("email_change_token_hash IS NOT NULL"),
        ),
        Index(
            "ix_users_pending_email",
            "pending_email",
            postgresql_where=text("pending_email IS NOT NULL"),
        ),
    )

    # CITEXT gives case-insensitive comparison at the DB layer; the app also
    # normalises (trim + lower) before storing. The unique constraint is named
    # ``uq_users_email`` by the metadata naming convention.
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    email_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Profile + preferences (spec 59).
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    editor_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Email-change confirmation (spec 59): only the token *hash* is stored, never
    # the raw token; the active email is unchanged until the token is confirmed.
    pending_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    email_change_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_change_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
