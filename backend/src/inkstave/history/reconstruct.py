"""Shared version reconstruction + text extraction (specs 36 & 37).

One place that turns (doc_id, version) → full Yjs state by replaying a chunk's
updates onto its base, and that extracts the document's text from a Yjs state — so
capture, diff and restore agree byte-for-byte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pycrdt import merge_updates
from sqlalchemy import select

from inkstave.collab.ydocument import YDocument
from inkstave.db.models.crdt import CrdtDocumentState, CrdtUpdate
from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.errors import NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.storage.base import ObjectStore


class HistoryVersionNotFound(NotFoundError):
    error_type = "history_version_not_found"

    def __init__(self, doc_id: UUID, version: int) -> None:
        super().__init__(f"No captured history for version {version}.")
        self.doc_id = doc_id
        self.version = version


def text_from_state(state: bytes) -> str:
    doc = YDocument()
    doc.apply_update(state)
    return doc.text


def is_binary(text: str) -> bool:
    return "\x00" in text


async def _read_blob(store: ObjectStore, key: str) -> bytes:
    parts = [part async for part in await store.get(key)]
    return b"".join(parts)


async def _chunk_base(store: ObjectStore, chunk: HistoryChunk) -> bytes:
    if chunk.base_snapshot is not None:
        return chunk.base_snapshot
    assert chunk.base_snapshot_blob_key is not None
    return await _read_blob(store, chunk.base_snapshot_blob_key)


async def _update_payload(store: ObjectStore, row: HistoryUpdate) -> bytes:
    if row.payload is not None:
        return row.payload
    assert row.payload_blob_key is not None
    return await _read_blob(store, row.payload_blob_key)


async def reconstruct_doc(
    session: AsyncSession, store: ObjectStore, doc_id: UUID, version: int
) -> YDocument:
    chunk = (
        await session.execute(
            select(HistoryChunk)
            .where(
                HistoryChunk.doc_id == doc_id,
                HistoryChunk.base_version <= version,
                HistoryChunk.end_version >= version,
            )
            .order_by(HistoryChunk.base_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if chunk is None:
        raise HistoryVersionNotFound(doc_id, version)
    doc = YDocument()
    doc.apply_update(await _chunk_base(store, chunk))
    rows = (
        await session.execute(
            select(HistoryUpdate)
            .where(
                HistoryUpdate.chunk_id == chunk.id,
                HistoryUpdate.version > chunk.base_version,
                HistoryUpdate.version <= version,
            )
            .order_by(HistoryUpdate.version)
        )
    ).scalars()
    for row in rows:
        doc.apply_update(await _update_payload(store, row))
    return doc


async def reconstruct_state(
    session: AsyncSession, store: ObjectStore, doc_id: UUID, version: int
) -> bytes:
    return (await reconstruct_doc(session, store, doc_id, version)).get_state()


async def load_current_state(session: AsyncSession, doc_id: UUID) -> bytes:
    """The live authoritative CRDT state from the spec-28 store (snapshot + log)."""
    state_row = await session.get(CrdtDocumentState, doc_id)
    updates = (
        await session.execute(
            select(CrdtUpdate.update)
            .where(CrdtUpdate.document_id == doc_id)
            .order_by(CrdtUpdate.id)
        )
    ).scalars()
    parts: list[bytes] = []
    if state_row is not None:
        parts.append(state_row.state)
    parts.extend(updates)
    if not parts:
        return YDocument().get_state()
    return merge_updates(*parts) if len(parts) > 1 else parts[0]


async def current_text(session: AsyncSession, doc_id: UUID) -> str:
    return text_from_state(await load_current_state(session, doc_id))
