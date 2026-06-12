"""History read service: list versions/updates and compute diffs (spec 37)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.db.models.history import HistoryLabel, HistoryUpdate
from inkstave.db.models.user import User
from inkstave.history.diff import diff_text
from inkstave.history.reconstruct import (
    HistoryVersionNotFound,
    current_text,
    is_binary,
    reconstruct_state,
    text_from_state,
)
from inkstave.schemas.history import (
    AuthorInfo,
    DiffResponse,
    LabelBrief,
    UpdateEntry,
    UpdatesResponse,
    VersionEntry,
    VersionsResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore


async def _max_version(session: AsyncSession, doc_id: UUID) -> int:
    value = await session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == doc_id)
    )
    return int(value) if value is not None else 0


async def _authors(session: AsyncSession, ids: set[UUID]) -> dict[UUID, AuthorInfo]:
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars()
    return {u.id: AuthorInfo(id=u.id, name=u.display_name, email=u.email) for u in rows}


async def list_versions(
    session: AsyncSession, doc_id: UUID, *, before: int | None, limit: int
) -> VersionsResponse:
    stmt = select(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id)
    if before is not None:
        stmt = stmt.where(HistoryUpdate.version < before)
    stmt = stmt.order_by(HistoryUpdate.version.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_before = rows[-1].version if has_more and rows else None

    authors = await _authors(session, {r.author_id for r in rows if r.author_id is not None})
    versions_in_page = [r.version for r in rows]
    labels_by_version = await _labels_for_versions(session, doc_id, versions_in_page)

    versions = [
        VersionEntry(
            version=r.version,
            timestamp=r.timestamp,
            author=authors.get(r.author_id) if r.author_id else None,
            op_count=r.op_count,
            size=r.payload_size,
            labels=labels_by_version.get(r.version, []),
        )
        for r in rows
    ]
    return VersionsResponse(
        doc_id=doc_id,
        current_version=await _max_version(session, doc_id),
        versions=versions,
        has_more=has_more,
        next_before=next_before,
    )


async def _labels_for_versions(
    session: AsyncSession, doc_id: UUID, versions: list[int]
) -> dict[int, list[LabelBrief]]:
    if not versions:
        return {}
    rows = (
        await session.execute(
            select(HistoryLabel).where(
                HistoryLabel.doc_id == doc_id, HistoryLabel.version.in_(versions)
            )
        )
    ).scalars()
    out: dict[int, list[LabelBrief]] = {}
    for label in rows:
        out.setdefault(label.version, []).append(LabelBrief(id=label.id, name=label.name))
    return out


async def list_updates(
    session: AsyncSession, doc_id: UUID, *, from_v: int | None, to_v: int | None
) -> UpdatesResponse:
    lo = from_v if from_v is not None else 1
    hi = to_v if to_v is not None else await _max_version(session, doc_id)
    rows = list(
        (
            await session.execute(
                select(HistoryUpdate)
                .where(
                    HistoryUpdate.doc_id == doc_id,
                    HistoryUpdate.version >= lo,
                    HistoryUpdate.version <= hi,
                )
                .order_by(HistoryUpdate.version)
            )
        ).scalars()
    )
    authors = await _authors(session, {r.author_id for r in rows if r.author_id is not None})
    return UpdatesResponse(
        doc_id=doc_id,
        updates=[
            UpdateEntry(
                version=r.version,
                timestamp=r.timestamp,
                author=authors.get(r.author_id) if r.author_id else None,
                op_count=r.op_count,
                size=r.payload_size,
            )
            for r in rows
        ],
    )


async def get_diff(
    session: AsyncSession,
    store: ObjectStore,
    settings: Settings,
    doc_id: UUID,
    *,
    from_v: int,
    to: int | str,
) -> DiffResponse:
    from_text = text_from_state(await reconstruct_state(session, store, doc_id, from_v))
    if to == "current":
        to_text = await current_text(session, doc_id)
        to_value: int | str = "current"
    else:
        assert isinstance(to, int)
        to_text = text_from_state(await reconstruct_state(session, store, doc_id, to))
        to_value = to

    limit = settings.history_diff_max_bytes
    base: dict[str, object] = {"from": from_v, "to": to_value}
    if len(from_text.encode("utf-8")) > limit or len(to_text.encode("utf-8")) > limit:
        return DiffResponse.model_validate(
            {**base, "binary": False, "too_large": True, "hunks": []}
        )
    if is_binary(from_text) or is_binary(to_text):
        return DiffResponse.model_validate({**base, "binary": True, "hunks": []})

    hunks = diff_text(from_text, to_text)
    return DiffResponse.model_validate({**base, "binary": False, "hunks": hunks})


__all__ = ["HistoryVersionNotFound", "get_diff", "list_updates", "list_versions"]
