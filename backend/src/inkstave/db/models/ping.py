"""The ``pings`` example model.

This table exists only to prove the migration workflow end-to-end (create,
upgrade, downgrade, autogenerate). Real domain models arrive with their own
feature specs.
"""

from __future__ import annotations

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Ping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pings"

    note: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("''"))
