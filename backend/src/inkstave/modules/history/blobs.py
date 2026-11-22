"""Removing a document's offloaded history blobs once its history rows are gone (spec 36 hardening).

Rows cascade with their document, but the blobs they point at live in object storage, which a
database cascade cannot reach. The keys are read before the delete, and the blobs are removed after
the commit: a rolled-back delete keeps its blobs, and a failed blob delete is logged, not raised.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import event, select

from inkstave.core.tasks import spawn
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.infra.storage.base import ObjectStore

logger = logging.getLogger(__name__)

_QUEUE_KEY = "history.blobs_to_purge"


async def _blob_keys(session: AsyncSession, doc_ids: list[UUID]) -> list[str]:
    chunk_keys = await session.scalars(
        select(HistoryChunk.base_snapshot_blob_key).where(
            HistoryChunk.doc_id.in_(doc_ids), HistoryChunk.base_snapshot_blob_key.is_not(None)
        )
    )
    update_keys = await session.scalars(
        select(HistoryUpdate.payload_blob_key).where(
            HistoryUpdate.doc_id.in_(doc_ids), HistoryUpdate.payload_blob_key.is_not(None)
        )
    )
    return [*chunk_keys, *update_keys]


async def purge_blobs_after_commit(
    session: AsyncSession, store: ObjectStore, doc_ids: Iterable[UUID]
) -> None:
    """Schedule the offloaded blobs of ``doc_ids`` for deletion once ``session`` commits.

    Call it before the documents are deleted, so their history rows are still readable. Ids that
    are not documents match nothing. Nothing is deleted if the transaction rolls back.
    """
    ids = list(doc_ids)
    if not ids:
        return
    keys = await _blob_keys(session, ids)
    if not keys:
        return
    queue = _queue(session)
    queue.extend((store, key) for key in keys)


async def purge_blobs_for_deleted(
    session: AsyncSession, store: ObjectStore | None, entity_ids: list[UUID]
) -> None:
    """The ``on_entities_deleted`` listener: purge the history of the entities a delete removes.

    Registered by the composition root. Without a store there is nothing to delete from.
    """
    if store is not None:
        await purge_blobs_after_commit(session, store, entity_ids)


def _queue(session: AsyncSession) -> list[tuple[ObjectStore, str]]:
    """The session's pending purges, registering its commit and rollback listeners on first use."""
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
    spawn(_delete_all(queue), name="history-blob-purge")


def _on_rollback(session: Any) -> None:
    if session.info.get(_QUEUE_KEY):
        session.info[_QUEUE_KEY] = []


async def _delete_all(queue: list[tuple[ObjectStore, str]]) -> None:
    for store, key in queue:
        try:
            await store.delete(key)
        except Exception:  # any storage backend's failure: log the orphan, keep deleting the rest
            logger.exception("could not delete history blob %s; it is orphaned", key)
