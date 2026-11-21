"""History capture service (spec 36).

Observes the CRDT update stream and records a compact, restorable version history
per document. Captures are debounced/coalesced in an in-process per-doc buffer so
live typing is never blocked: ``capture_update`` only mutates memory + (re)arms a
timer; the DB write happens on ``flush_doc``.

History is stored as **chunks** (a base snapshot + the ordered incremental updates
after it). A per-doc replica `Y.Doc`, built from the captured stream, supplies the
full state for chunk base snapshots. The very first chunk starts from the live CRDT
state, so content the document had before its first edit is part of the history.
Any version is reconstructed by replaying a chunk's updates onto its base; see
``docs/adr/0036-history-capture.md`` for the chunking/merge trade-offs.

A flush that changes nothing records no version. A replica rebuilt from the database
whose text disagrees with the live document (history captured before the live seed
was, or drift) is re-based: its chunk is sealed and the next one starts from the live
state, so later versions reconstruct correctly.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pycrdt import merge_updates
from sqlalchemy import func, select

from inkstave.core.invariants import require
from inkstave.core.tasks import spawn
from inkstave.modules.collab import YDocument
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate
from inkstave.modules.history.versions.capture_values import Pending, Replica, UpdateEntry, doc_from
from inkstave.modules.history.versions.reconstruct import load_live_state, reconstruct_doc, reconstruct_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore

    SessionFactory = Callable[[], Any]

FlushReason = Literal["idle", "shutdown", "threshold", "manual"]


def _sha256_digest(data: bytes) -> bytes:
    """SHA-256 raw digest, isolated so it can run via ``asyncio.to_thread``."""
    return hashlib.sha256(data).digest()


@dataclass
class _DocBuffer:
    updates: list[bytes] = field(default_factory=list)
    author_id: UUID | None = None
    origin: str | None = None
    last_at: datetime | None = None
    timer: asyncio.TimerHandle | None = None


class HistoryCaptureService:
    def __init__(
        self, session_factory: SessionFactory, object_store: ObjectStore, settings: Settings
    ) -> None:
        self._session_factory = session_factory
        self._store = object_store
        self._settings = settings
        self._buffers: dict[UUID, _DocBuffer] = {}
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._last_hash: dict[UUID, bytes] = {}
        self._project_ids: dict[UUID, UUID] = {}
        self._replicas: dict[UUID, YDocument] = {}

    def _lock(self, doc_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(doc_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[doc_id] = lock
        return lock

    async def capture_update(
        self,
        *,
        project_id: UUID,
        doc_id: UUID,
        update: bytes,
        author_id: UUID | None,
        at: datetime,
        origin: str | None = None,
    ) -> None:
        """Buffer one raw server-applied update; returns without any DB write."""
        async with self._lock(doc_id):
            digest = await asyncio.to_thread(_sha256_digest, update)
            if self._last_hash.get(doc_id) == digest:
                return  # de-dupe an immediately-repeated raw update (reconnect replay)
            self._last_hash[doc_id] = digest

            buf = self._buffers.setdefault(doc_id, _DocBuffer())
            buf.updates.append(update)
            buf.author_id = author_id
            buf.origin = origin
            buf.last_at = at
            self._project_ids[doc_id] = project_id
            over_threshold = len(buf.updates) >= self._settings.history_flush_max_buffer
            self._arm_timer(doc_id, buf)

        if over_threshold:
            await self.flush_doc(doc_id=doc_id, reason="threshold")

    def _arm_timer(self, doc_id: UUID, buf: _DocBuffer) -> None:
        if buf.timer is not None:
            buf.timer.cancel()
        delay = self._settings.history_debounce_ms / 1000
        buf.timer = asyncio.get_running_loop().call_later(delay, self._on_timer, doc_id)

    def _on_timer(self, doc_id: UUID) -> None:
        # Fire-and-forget by design: a failed flush is logged and retried by the next edit
        # or the periodic compaction job.
        spawn(self.flush_doc(doc_id=doc_id, reason="idle"), name="history-idle-flush")

    def _take(self, doc_id: UUID) -> Pending | None:
        """Detach the doc's buffer and return its merged contents, if any."""
        buf = self._buffers.get(doc_id)
        if buf is None or not buf.updates:
            return None
        if buf.timer is not None:
            buf.timer.cancel()
        self._buffers.pop(doc_id, None)
        raw = buf.updates
        return Pending(
            merged=merge_updates(*raw) if len(raw) > 1 else raw[0],
            op_count=len(raw),
            author_id=buf.author_id,
            at=buf.last_at or _utcnow(),
            project_id=self._project_ids[doc_id],
            origin=buf.origin,
        )

    async def _write(self, doc_id: UUID, pending: Pending) -> None:
        """Append the pending update to the open chunk, sealing it when it is full."""
        async with self._session_factory() as session:
            open_chunk = await self._open_chunk(session, doc_id)
            replica = await self._replica(session, doc_id, open_chunk)
            before = replica.doc.get_state()
            replica.doc.apply_update(pending.merged)
            drifted = replica.drifted_from_live()
            if not (drifted or replica.from_live or replica.doc.get_state() != before):
                return  # nothing changed: an empty sync step or a replayed update
            next_v = await self._max_version(session, doc_id) + 1
            if open_chunk is None:
                open_chunk = await self._new_chunk(
                    session, pending.project_id, doc_id, before, base_version=next_v - 1
                )
            await self._insert_update(session, UpdateEntry.of(open_chunk, doc_id, next_v, pending))
            open_chunk.end_version = next_v
            await self._maybe_seal(session, open_chunk, replica, drifted)
            await session.commit()

    async def _maybe_seal(
        self, session: AsyncSession, chunk: HistoryChunk, replica: Replica, drifted: bool
    ) -> None:
        """Seal ``chunk`` when it is full, or re-base it on the live state when the replica drifted."""
        if drifted:
            state = require(replica.live, "a drifted replica always has a live state")
            self._replicas[chunk.doc_id] = doc_from(state)
        elif chunk.end_version - chunk.start_version + 1 >= self._settings.history_chunk_max_updates:
            state = replica.doc.get_state()
        else:
            return
        chunk.sealed = True
        await session.flush()  # free the partial-unique open-chunk index
        await self._new_chunk(session, chunk.project_id, chunk.doc_id, state, base_version=chunk.end_version)

    async def flush_doc(self, *, doc_id: UUID, reason: FlushReason) -> None:
        async with self._lock(doc_id):
            pending = self._take(doc_id)
            if pending is not None:
                await self._write(doc_id, pending)
            if reason in ("idle", "shutdown"):
                self._drop_state(doc_id)

    async def flush_all(self) -> None:
        for doc_id in list(self._buffers):
            await self.flush_doc(doc_id=doc_id, reason="shutdown")

    def _drop_state(self, doc_id: UUID) -> None:
        self._replicas.pop(doc_id, None)
        self._last_hash.pop(doc_id, None)
        self._buffers.pop(doc_id, None)
        self._locks.pop(doc_id, None)
        self._project_ids.pop(doc_id, None)

    async def reconstruct_state(self, *, doc_id: UUID, version: int) -> bytes:
        async with self._session_factory() as session:
            return await reconstruct_state(session, self._store, doc_id, version)

    async def _replica(self, session: AsyncSession, doc_id: UUID, open_chunk: HistoryChunk | None) -> Replica:
        """The doc's replica at the head of its history, rebuilt from the database when not in memory."""
        cached = self._replicas.get(doc_id)
        if cached is not None:
            return Replica(cached)
        live = await load_live_state(session, doc_id)
        if open_chunk is None:
            replica = Replica(doc_from(live), live=live, from_live=live is not None)
        else:
            doc = await reconstruct_doc(session, self._store, doc_id, open_chunk.end_version)
            replica = Replica(doc, live=live)
        self._replicas[doc_id] = replica.doc
        return replica

    async def _open_chunk(self, session: AsyncSession, doc_id: UUID) -> HistoryChunk | None:
        return (
            await session.execute(
                select(HistoryChunk).where(HistoryChunk.doc_id == doc_id, HistoryChunk.sealed.is_(False))
            )
        ).scalar_one_or_none()

    async def _max_version(self, session: AsyncSession, doc_id: UUID) -> int:
        value = (
            await session.execute(
                select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == doc_id)
            )
        ).scalar_one_or_none()
        return int(value) if value is not None else 0

    async def _new_chunk(
        self,
        session: AsyncSession,
        project_id: UUID,
        doc_id: UUID,
        base_state: bytes,
        *,
        base_version: int,
    ) -> HistoryChunk:
        snapshot, blob_key = await self._store_payload(base_state, self._is_oversized(base_state))
        chunk = HistoryChunk(
            project_id=project_id,
            doc_id=doc_id,
            start_version=base_version + 1,
            end_version=base_version,
            base_version=base_version,
            base_snapshot=snapshot,
            base_snapshot_blob_key=blob_key,
            base_snapshot_size=len(base_state),
            sealed=False,
        )
        session.add(chunk)
        await session.flush()
        return chunk

    def _is_oversized(self, payload: bytes) -> bool:
        return len(payload) > self._settings.history_inline_max_bytes

    async def _store_payload(self, payload: bytes, offload: bool) -> tuple[bytes | None, str | None]:
        if not offload:
            return payload, None
        key = f"{self._settings.history_blob_prefix}{uuid.uuid4().hex}"
        await self._store.put(key, payload, content_type="application/octet-stream")
        return None, key

    async def _insert_update(self, session: AsyncSession, entry: UpdateEntry) -> None:
        """Persist one history update, offloading an oversized payload to the store."""
        inline, blob_key = await self._store_payload(entry.payload, self._is_oversized(entry.payload))
        session.add(
            HistoryUpdate(
                chunk_id=entry.chunk.id,
                project_id=entry.project_id,
                doc_id=entry.doc_id,
                version=entry.version,
                timestamp=entry.at,
                author_id=entry.author_id,
                payload=inline,
                payload_blob_key=blob_key,
                payload_size=len(entry.payload),
                op_count=entry.op_count,
                origin=entry.origin,
            )
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)
