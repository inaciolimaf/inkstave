"""The ``auth_tokens`` table — single-use, hashed-at-rest link tokens (spec 104).

One table backs all three email-link flows (verify / magic-login / reset). Only
the SHA-256 *hash* of the token is stored; the raw token exists only inside the
emailed URL. A row is "spent" once ``consumed_at`` is set (single-use); expiry is
``created_at + per-purpose TTL``. The spec-59 email-change token stays on the
``users`` row — this table generalises the *pattern*, not that single token.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from inkstave.db.models.user import User

# The three link purposes. A token issued for one purpose can never be redeemed
# at another flow's callback (the consume path filters by purpose).
PURPOSES = ("email_verify", "magic_login", "password_reset")


class AuthToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_tokens"

    __table_args__ = (
        # Single lookup key; the raw token is never queried, only its hash.
        Index("uq_auth_tokens_token_hash", "token_hash", unique=True),
        # Cheap "invalidate older tokens of this purpose for this user".
        Index("ix_auth_tokens_user_purpose", "user_id", "purpose"),
        # Forward-looking partial index for a future expiry sweep (sweep itself is
        # out of scope; mirrors the partial-index style used on ``users``).
        Index(
            "ix_auth_tokens_active",
            "purpose",
            "expires_at",
            postgresql_where=text("consumed_at IS NULL"),
        ),
        CheckConstraint(
            "purpose IN ('email_verify','magic_login','password_reset')",
            name="ck_auth_tokens_purpose",
        ),
    )

    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_auth_tokens_user_id_users"),
        nullable=False,
    )
    # The address the link was issued for — bound at creation so a later email
    # change cannot be confirmed by an old link.
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()
