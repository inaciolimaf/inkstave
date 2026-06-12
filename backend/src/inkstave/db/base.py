"""Declarative base, shared metadata naming convention, and model mixins.

A single :class:`~sqlalchemy.MetaData` carries the constraint **naming
convention** so Alembic emits stable, predictable constraint names across every
table. All models inherit :class:`Base`; most also mix in
:class:`UUIDPrimaryKeyMixin` and :class:`TimestampMixin`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Registered on the metadata so generated constraints are deterministically
# named (important for stable Alembic autogenerate diffs).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base sharing the project-wide metadata/naming convention."""

    metadata = metadata


class UUIDPrimaryKeyMixin:
    """Adds a UUID v4 primary key named ``id`` (generated app-side)."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Adds timezone-aware ``created_at`` / ``updated_at`` columns."""

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        # ``updated_at`` carries a server-side ``onupdate``: after an UPDATE the ORM
        # expires the attribute and would refresh it lazily on next access. Under the
        # async engine that lazy SELECT raises ``MissingGreenlet``. ``eager_defaults``
        # makes INSERT/UPDATE fetch server-generated values back via RETURNING, so the
        # timestamps stay loaded and serialising the row never triggers blocking IO.
        return {"eager_defaults": True}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
