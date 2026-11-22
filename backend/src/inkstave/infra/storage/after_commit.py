"""Object deletes that run once a database transaction commits, and never on rollback.

Storage is not transactional: a row that names a blob must be gone before the blob is deleted, or a
rolled-back delete leaves a row pointing at nothing. Callers queue the keys on their session; the
session's commit starts the deletes in the background, a rollback drops them, and a failed delete is
logged (the orphan stays) rather than raised, since the request has already succeeded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import event

from inkstave.core.tasks import spawn

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.infra.storage.base import ObjectStore

logger = logging.getLogger(__name__)

_QUEUE_KEY = "storage.deletes_after_commit"


def schedule_delete_after_commit(session: AsyncSession, store: ObjectStore, keys: Iterable[str]) -> None:
    """Delete ``keys`` from ``store`` once ``session`` commits. Nothing is deleted if it rolls back."""
    _queue(session).extend((store, key) for key in keys)


def _queue(session: AsyncSession) -> list[tuple[ObjectStore, str]]:
    """The session's pending deletes, registering its commit and rollback listeners on first use."""
    info: dict[str, Any] = session.sync_session.info
    if _QUEUE_KEY not in info:
        info[_QUEUE_KEY] = []
        event.listen(session.sync_session, "after_commit", _on_commit)
        event.listen(session.sync_session, "after_rollback", _on_rollback)
    queue: list[tuple[ObjectStore, str]] = info[_QUEUE_KEY]
    return queue


def _on_commit(session: Any) -> None:  # the sync session, which the architecture test keeps out of imports
    queue: list[tuple[ObjectStore, str]] = session.info.get(_QUEUE_KEY) or []
    if not queue:
        return
    session.info[_QUEUE_KEY] = []
    spawn(_delete_all(queue), name="storage-delete-after-commit")


def _on_rollback(session: Any) -> None:
    if session.info.get(_QUEUE_KEY):
        session.info[_QUEUE_KEY] = []


async def _delete_all(queue: list[tuple[ObjectStore, str]]) -> None:
    for store, key in queue:
        try:
            await store.delete(key)
        except Exception:  # any storage backend's failure: log the orphan, keep deleting the rest
            logger.exception("could not delete blob %s; it is orphaned", key)
