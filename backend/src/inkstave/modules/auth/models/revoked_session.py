"""Sessions ended by a logout, kept until their last possible token has expired."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.core.db.base import Base


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"
    __table_args__ = (Index("ix_revoked_sessions_expires_at", "expires_at"),)

    session_id: Mapped[UUID] = mapped_column(primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
