"""The user's record or 404: one way to load it, so a check cannot be forgotten."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.errors import AppError


async def get_owned[T](
    session: AsyncSession,
    model: type[T],
    record_id: UUID,
    user_id: UUID,
    *,
    not_found: AppError,
    **scope: Any,
) -> T:
    """Fetch by id and owner, plus any ``scope`` columns.

    Nonexistent and someone else's raise the same ``not_found``, so a response never reveals
    that an id exists. ``model`` must have ``id`` and ``user_id`` columns.
    """
    conditions = [
        model.id == record_id,  # type: ignore[attr-defined]
        model.user_id == user_id,  # type: ignore[attr-defined]
        *(getattr(model, column) == value for column, value in scope.items()),
    ]
    record = await session.scalar(select(model).where(*conditions))
    if record is None:
        raise not_found
    return record
