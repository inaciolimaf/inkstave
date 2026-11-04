"""Git access tables: personal access tokens and the per-project repository record (spec 121).

``git_access_tokens`` holds only the SHA-256 hash of a token; the raw value is shown once at creation.
``git_repo_state`` records what ``main`` was after the last snapshot or accepted push.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base, UUIDPrimaryKeyMixin


class GitAccessToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "git_access_tokens"

    __table_args__ = (
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_length"),
        Index("uq_git_access_tokens_token_hash", "token_hash", unique=True),
        Index("ix_git_access_tokens_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_git_access_tokens_user_id_users"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # The first 12 characters of the token, kept for display ("ink_abc1234…").
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GitRepoState(Base):
    __tablename__ = "git_repo_state"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_git_repo_state_project_id_projects"),
        primary_key=True,
    )
    # The commit sha `main` pointed to after the last snapshot or accepted push.
    head: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
