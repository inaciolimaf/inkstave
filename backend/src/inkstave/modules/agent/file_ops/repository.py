"""Queries for proposed file operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from inkstave.modules.agent.file_ops.models import ProposedFileOp, ProposedFileOpStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def mark_superseded(db: AsyncSession, *, session_id: UUID, path: str) -> None:
    """A new proposal on a path replaces the session's open one on the same path."""
    await db.execute(
        update(ProposedFileOp)
        .where(
            ProposedFileOp.session_id == session_id,
            ProposedFileOp.path == path,
            ProposedFileOp.status == ProposedFileOpStatus.proposed.value,
        )
        .values(status=ProposedFileOpStatus.superseded.value)
    )


async def list_for_session(db: AsyncSession, session_id: UUID) -> list[ProposedFileOp]:
    """The session's operations in proposal order, without the ones later replaced."""
    rows = await db.execute(
        select(ProposedFileOp)
        .where(
            ProposedFileOp.session_id == session_id,
            ProposedFileOp.status != ProposedFileOpStatus.superseded.value,
        )
        .order_by(ProposedFileOp.created_at)
    )
    return list(rows.scalars())


async def get_for_session(db: AsyncSession, session_id: UUID, op_id: UUID) -> ProposedFileOp | None:
    row = await db.get(ProposedFileOp, op_id, with_for_update=True)
    return row if row is not None and row.session_id == session_id else None
