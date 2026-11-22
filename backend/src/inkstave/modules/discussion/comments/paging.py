"""Paging of comment threads (spec 118): oldest first, keyed on ``(created_at, id)``.

The cursor is opaque to clients. It names the last thread of a page, so a thread deleted between two
pages (its last message removed) does not break the next one. A thread created during paging sorts
after the cursor and shows up on a later page, as the ordering promises.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import literal, select, tuple_

from inkstave.modules.discussion.comments.errors import InvalidCursorError
from inkstave.modules.discussion.comments.models import CommentThread

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def encode_cursor(thread: CommentThread) -> str:
    raw = f"{thread.created_at.isoformat()}|{thread.id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        stamp, _, raw_id = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8").partition("|")
        return datetime.fromisoformat(stamp), UUID(raw_id)
    except ValueError as exc:  # binascii, unicode and uuid errors are all ValueErrors
        raise InvalidCursorError() from exc


async def page_threads(
    session: AsyncSession,
    project_id: UUID,
    *,
    document_id: UUID | None,
    status: str,
    limit: int,
    after: str | None,
) -> tuple[list[CommentThread], str | None]:
    """One page of threads and the cursor for the next one (``None`` on the last page)."""
    statement = select(CommentThread).where(CommentThread.project_id == project_id)
    if document_id is not None:
        statement = statement.where(CommentThread.document_id == document_id)
    if status == "open":
        statement = statement.where(CommentThread.resolved_at.is_(None))
    elif status == "resolved":
        statement = statement.where(CommentThread.resolved_at.is_not(None))
    if after is not None:
        stamp, thread_id = decode_cursor(after)
        statement = statement.where(
            tuple_(CommentThread.created_at, CommentThread.id) > tuple_(literal(stamp), literal(thread_id))
        )
    statement = statement.order_by(CommentThread.created_at, CommentThread.id).limit(limit + 1)
    rows = list((await session.execute(statement)).scalars())
    if len(rows) <= limit:
        return rows, None
    page = rows[:limit]
    return page, encode_cursor(page[-1])
