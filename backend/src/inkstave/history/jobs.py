"""The history compaction ARQ job (spec 36).

Safe to re-run (idempotent). It (1) merges runs of adjacent tiny updates within
*sealed* chunks into one row keeping the highest version + summed op_count, and
(2) offloads any oversized inline payload/snapshot to blob storage. It never
reduces the set of reconstructible versions except that merged-away intermediate
versions stop being individually addressable (documented in the ADR).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pycrdt import merge_updates
from sqlalchemy import func, select

from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.history.reconstruct import reconstruct_state
from inkstave.invariants import require
from inkstave.storage.factory import get_object_store

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore


async def compact_history(ctx: dict[str, Any], doc_id: str | None = None) -> dict[str, Any]:
    settings: Settings = ctx["settings"]
    store: ObjectStore = ctx.get("object_store") or get_object_store(settings)
    session_factory = ctx["session_factory"]

    result = {"docs": 0, "merged_rows": 0, "offloaded": 0}
    dead_blobs: list[str] = []

    async with session_factory() as session:
        if doc_id is not None:
            targets = [UUID(doc_id)]
        else:
            targets = await _docs_needing_compaction(session, settings.history_compact_min_updates)
        for target in targets:
            merged, offloaded, blobs = await _compact_doc(session, store, settings, target)
            result["merged_rows"] += merged
            result["offloaded"] += offloaded
            result["docs"] += 1
            dead_blobs.extend(blobs)
        await session.commit()

    # Blob deletes are idempotent; do them after the row changes are committed.
    for key in dead_blobs:
        await store.delete(key)
    return result


async def _docs_needing_compaction(session: AsyncSession, min_updates: int) -> list[UUID]:
    rows = (
        await session.execute(
            select(HistoryUpdate.doc_id)
            .group_by(HistoryUpdate.doc_id)
            .having(func.count() >= min_updates)
        )
    ).scalars()
    return list(rows)


async def _read(store: ObjectStore, row: HistoryUpdate) -> bytes:
    if row.payload is not None:
        return row.payload
    key = require(row.payload_blob_key, f"history update {row.id} has no payload and no blob key")
    parts = [part async for part in await store.get(key)]
    return b"".join(parts)


def _tiny_runs(rows: list[HistoryUpdate], merge_bytes: int) -> Iterator[list[HistoryUpdate]]:
    """Maximal runs of >= 2 adjacent updates that are each smaller than `merge_bytes`."""
    i = 0
    while i < len(rows):
        if rows[i].payload_size >= merge_bytes:
            i += 1
            continue
        j = i
        while j + 1 < len(rows) and rows[j + 1].payload_size < merge_bytes:
            j += 1
        if j > i:
            yield rows[i : j + 1]
        i = j + 1


async def _merge_run(
    session: AsyncSession, store: ObjectStore, settings: Settings, run: list[HistoryUpdate]
) -> list[str]:
    """Collapse one run into its last row; returns the blob keys left dangling."""
    payloads = [await _read(store, r) for r in run]
    merged = merge_updates(*payloads)
    dead = [r.payload_blob_key for r in run if r.payload_blob_key is not None]
    for r in run[:-1]:
        await session.delete(r)
    keep = run[-1]
    inline, blob_key = await _store(
        store, merged, settings.history_blob_prefix, len(merged) > settings.history_inline_max_bytes
    )
    keep.payload = inline
    keep.payload_blob_key = blob_key
    keep.payload_size = len(merged)
    keep.op_count = sum(r.op_count for r in run)
    return dead


async def _merge_sealed_chunks(
    session: AsyncSession, store: ObjectStore, settings: Settings, doc_id: UUID
) -> tuple[int, list[str]]:
    """Merge adjacent tiny updates inside every sealed chunk of a document."""
    merged_rows = 0
    dead_blobs: list[str] = []
    sealed_chunks = (
        await session.execute(
            select(HistoryChunk).where(HistoryChunk.doc_id == doc_id, HistoryChunk.sealed.is_(True))
        )
    ).scalars()
    for chunk in sealed_chunks:
        rows = list(
            (
                await session.execute(
                    select(HistoryUpdate)
                    .where(HistoryUpdate.chunk_id == chunk.id)
                    .order_by(HistoryUpdate.version)
                )
            ).scalars()
        )
        for run in list(_tiny_runs(rows, settings.history_compact_merge_bytes)):
            dead_blobs += await _merge_run(session, store, settings, run)
            merged_rows += len(run) - 1
        await session.flush()
    return merged_rows, dead_blobs


async def _offload_updates(
    session: AsyncSession, store: ObjectStore, settings: Settings, doc_id: UUID
) -> int:
    """Move oversized inline update payloads to the blob store (idempotent)."""
    inline_max = settings.history_inline_max_bytes
    oversized = (
        await session.execute(
            select(HistoryUpdate).where(
                HistoryUpdate.doc_id == doc_id,
                HistoryUpdate.payload.is_not(None),
                HistoryUpdate.payload_size > inline_max,
            )
        )
    ).scalars()
    count = 0
    for row in oversized:
        payload = require(row.payload, f"history update {row.id} lost its payload mid-sweep")
        _, key = await _store(store, payload, settings.history_blob_prefix, offload=True)
        row.payload = None
        row.payload_blob_key = key
        count += 1
    return count


async def _offload_snapshots(
    session: AsyncSession, store: ObjectStore, settings: Settings, doc_id: UUID
) -> int:
    """Move oversized inline chunk snapshots to the blob store (idempotent)."""
    big_chunks = (
        await session.execute(
            select(HistoryChunk).where(
                HistoryChunk.doc_id == doc_id,
                HistoryChunk.base_snapshot.is_not(None),
                HistoryChunk.base_snapshot_size > settings.history_inline_max_bytes,
            )
        )
    ).scalars()
    count = 0
    for chunk in big_chunks:
        snapshot = require(chunk.base_snapshot, f"chunk {chunk.id} lost its snapshot mid-sweep")
        _, key = await _store(store, snapshot, settings.history_blob_prefix, offload=True)
        chunk.base_snapshot = None
        chunk.base_snapshot_blob_key = key
        count += 1
    return count


async def _compact_doc(
    session: AsyncSession, store: ObjectStore, settings: Settings, doc_id: UUID
) -> tuple[int, int, list[str]]:
    # §5.4.2 step 2: seal the open tail if it overflowed without inline-sealing
    # (e.g. an interrupted/multi-worker flush). Done first so the freshly sealed
    # chunk is eligible for the merge/offload pass below in this same run.
    await _seal_open_tail(session, store, settings, doc_id)

    merged_rows, dead_blobs = await _merge_sealed_chunks(session, store, settings, doc_id)
    offloaded = await _offload_updates(session, store, settings, doc_id)
    offloaded += await _offload_snapshots(session, store, settings, doc_id)
    return merged_rows, offloaded, dead_blobs


async def _seal_open_tail(
    session: AsyncSession, store: ObjectStore, settings: Settings, doc_id: UUID
) -> None:
    """Seal the open chunk if it grew past the max-updates threshold (§5.4.2 step 2).

    ``flush_doc`` normally seals inline once a chunk reaches
    ``history_chunk_max_updates``; this is the compaction-side safety net for when
    that inline seal did not fire (interrupted or multi-worker flush). When the
    open tail is oversized we seal it and start a fresh open chunk (mirroring the
    capture service's seal-and-reopen) so it becomes eligible for offload/merge.
    """
    open_chunk = (
        await session.execute(
            select(HistoryChunk).where(
                HistoryChunk.doc_id == doc_id, HistoryChunk.sealed.is_(False)
            )
        )
    ).scalar_one_or_none()
    if open_chunk is None:
        return

    update_count = int(
        await session.scalar(
            select(func.count())
            .select_from(HistoryUpdate)
            .where(HistoryUpdate.chunk_id == open_chunk.id)
        )
        or 0
    )
    if update_count < settings.history_chunk_max_updates:
        return

    open_chunk.sealed = True
    await session.flush()  # free the partial-unique open-chunk index before reopening
    await _reopen_after(session, store, settings, doc_id, open_chunk)


async def _reopen_after(
    session: AsyncSession,
    store: ObjectStore,
    settings: Settings,
    doc_id: UUID,
    sealed: HistoryChunk,
) -> None:
    """Start a fresh open chunk snapshotted at the just-sealed chunk's end version."""
    base_state = await reconstruct_state(session, store, doc_id, sealed.end_version)
    snapshot, blob_key = await _store(
        store,
        base_state,
        settings.history_blob_prefix,
        len(base_state) > settings.history_inline_max_bytes,
    )
    session.add(
        HistoryChunk(
            project_id=sealed.project_id,
            doc_id=doc_id,
            start_version=sealed.end_version + 1,
            end_version=sealed.end_version,
            base_version=sealed.end_version,
            base_snapshot=snapshot,
            base_snapshot_blob_key=blob_key,
            base_snapshot_size=len(base_state),
            sealed=False,
        )
    )
    await session.flush()


async def _store(
    store: ObjectStore, payload: bytes, prefix: str, offload: bool
) -> tuple[bytes | None, str | None]:
    if not offload:
        return payload, None
    key = f"{prefix}{uuid.uuid4().hex}"
    await store.put(key, payload, content_type="application/octet-stream")
    return None, key
