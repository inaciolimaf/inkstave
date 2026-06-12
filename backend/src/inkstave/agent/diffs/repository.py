"""Persistence + queries for proposed diffs (spec 43). Used by specs 44/47."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select, update

from inkstave.agent.diffs.models import ProposedDiff, ProposedDiffStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create(
    db: AsyncSession,
    *,
    session_id: UUID,
    message_id: UUID | None,
    project_id: UUID,
    doc_id: UUID,
    path: str,
    base_version: str,
    base_hash: str,
    diff_text: str,
    hunks: list[dict[str, Any]],
    stats: dict[str, int],
    status: str = ProposedDiffStatus.proposed.value,
    rationale: str | None = None,
) -> ProposedDiff:
    row = ProposedDiff(
        session_id=session_id,
        message_id=message_id,
        project_id=project_id,
        doc_id=doc_id,
        path=path,
        base_version=base_version,
        base_hash=base_hash,
        diff_text=diff_text,
        hunks=hunks,
        stats=stats,
        status=status,
        rationale=rationale,
    )
    db.add(row)
    await db.flush()
    return row


async def mark_superseded(db: AsyncSession, *, session_id: UUID, doc_id: UUID) -> int:
    """Supersede prior open proposals for the same (session, doc)."""
    result = await db.execute(
        update(ProposedDiff)
        .where(
            ProposedDiff.session_id == session_id,
            ProposedDiff.doc_id == doc_id,
            ProposedDiff.status == ProposedDiffStatus.proposed.value,
        )
        .values(status=ProposedDiffStatus.superseded.value)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def list_for_session(db: AsyncSession, session_id: UUID) -> list[ProposedDiff]:
    rows = await db.execute(
        select(ProposedDiff)
        .where(ProposedDiff.session_id == session_id)
        .order_by(ProposedDiff.created_at)
    )
    return list(rows.scalars())


async def list_open_for_project(db: AsyncSession, project_id: UUID) -> list[ProposedDiff]:
    rows = await db.execute(
        select(ProposedDiff).where(
            ProposedDiff.project_id == project_id,
            ProposedDiff.status == ProposedDiffStatus.proposed.value,
        )
    )
    return list(rows.scalars())


async def get(db: AsyncSession, diff_id: UUID) -> ProposedDiff | None:
    return await db.get(ProposedDiff, diff_id)


async def set_status(
    db: AsyncSession,
    diff_id: UUID,
    status: str,
    *,
    applied_hunk_ids: list[str] | None = None,
) -> ProposedDiff | None:
    row = await db.get(ProposedDiff, diff_id)
    if row is None:
        return None
    row.status = status
    if applied_hunk_ids is not None:
        # Record which hunks were applied for partial applies (spec 47).
        stats = dict(row.stats)
        stats["applied_hunk_ids"] = applied_hunk_ids
        row.stats = stats
    await db.flush()
    return row
