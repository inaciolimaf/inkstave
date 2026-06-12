"""History capture service (spec 36).

Observes the CRDT update stream and records a compact, restorable version history
per document. Captures are debounced/coalesced in an in-process per-doc buffer so
live typing is never blocked: ``capture_update`` only mutates memory + (re)arms a
timer; the DB write happens on ``flush_doc``.

History is stored as **chunks** (a base snapshot + the ordered incremental updates
after it). A per-doc replica `Y.Doc`, built from the captured stream, supplies the
full state for chunk base snapshots (empty for the very first chunk). Any version
is reconstructed by replaying a chunk's updates onto its base; see
``docs/adr/0036-history-capture.md`` for the chunking/merge trade-offs.
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

from inkstave.collab.ydocument import YDocument
from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.history.reconstruct import reconstruct_doc, reconstruct_state

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore

    SessionFactory = Callable[[], Any]

FlushReason = Literal["idle", "shutdown", "threshold", "manual"]


@dataclass
class _DocBuffer:
    updates: list[bytes] = field(default_factory=list)
    author_id: UUID | None = None
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

    # --- capture (non-blocking) -------------------------------------------- #

    async def capture_update(
        self,
        *,
        project_id: UUID,
        doc_id: UUID,
        update: bytes,
        author_id: UUID | None,
        at: datetime,
    ) -> None:
        """Buffer one raw server-applied update; returns without any DB write."""
        async with self._lock(doc_id):
            digest = hashlib.sha256(update).digest()
            if self._last_hash.get(doc_id) == digest:
                return  # de-dupe an immediately-repeated raw update (reconnect replay)
            self._last_hash[doc_id] = digest

            buf = self._buffers.setdefault(doc_id, _DocBuffer())
            buf.updates.append(update)
            buf.author_id = author_id
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
        asyncio.ensure_future(self.flush_doc(doc_id=doc_id, reason="idle"))  # noqa: RUF006

    # --- flush (the actual write) ------------------------------------------ #

    async def flush_doc(self, *, doc_id: UUID, reason: FlushReason) -> None:
        async with self._lock(doc_id):
            buf = self._buffers.get(doc_id)
            if buf is None or not buf.updates:
                if reason in ("idle", "shutdown"):
                    self._drop_state(doc_id)
                return
            raw = buf.updates
            author = buf.author_id
            at = buf.last_at or _utcnow()
            project_id = self._project_ids[doc_id]
            if buf.timer is not None:
                buf.timer.cancel()
            self._buffers.pop(doc_id, None)

            merged = merge_updates(*raw) if len(raw) > 1 else raw[0]

            async with self._session_factory() as session:
                open_chunk = await self._open_chunk(session, doc_id)
                replica = await self._replica(session, doc_id, open_chunk)
                max_v = await self._max_version(session, doc_id)
                next_v = max_v + 1

                if open_chunk is None:
                    open_chunk = await self._new_chunk(
                        session, project_id, doc_id, replica.get_state(), base_version=max_v
                    )

                replica.apply_update(merged)
                await self._insert_update(
                    session,
                    chunk=open_chunk,
                    project_id=project_id,
                    doc_id=doc_id,
                    version=next_v,
                    payload=merged,
                    op_count=len(raw),
                    author_id=author,
                    at=at,
                )
                open_chunk.end_version = next_v

                in_chunk = next_v - open_chunk.start_version + 1
                if in_chunk >= self._settings.history_chunk_max_updates:
                    open_chunk.sealed = True
                    await session.flush()  # free the partial-unique open-chunk index
                    await self._new_chunk(
                        session, project_id, doc_id, replica.get_state(), base_version=next_v
                    )

                await session.commit()

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

    async def ensure_snapshot(
        self, *, project_id: UUID, doc_id: UUID, current_state: bytes, version: int
    ) -> None:
        """Public seal-and-reopen primitive (spec 37 may drive snapshots explicitly)."""
        async with self._lock(doc_id), self._session_factory() as session:
            open_chunk = await self._open_chunk(session, doc_id)
            if open_chunk is not None:
                open_chunk.sealed = True
                await session.flush()
            await self._new_chunk(session, project_id, doc_id, current_state, base_version=version)
            await session.commit()

    # --- reconstruction (used by spec 37 + our own tests) ------------------ #

    async def reconstruct_state(self, *, doc_id: UUID, version: int) -> bytes:
        async with self._session_factory() as session:
            return await reconstruct_state(session, self._store, doc_id, version)

    # --- helpers ----------------------------------------------------------- #

    async def _replica(
        self, session: AsyncSession, doc_id: UUID, open_chunk: HistoryChunk | None
    ) -> YDocument:
        replica = self._replicas.get(doc_id)
        if replica is None:
            if open_chunk is not None:
                replica = await reconstruct_doc(
                    session, self._store, doc_id, open_chunk.end_version
                )
            else:
                replica = YDocument()
            self._replicas[doc_id] = replica
        return replica

    async def _open_chunk(self, session: AsyncSession, doc_id: UUID) -> HistoryChunk | None:
        return (
            await session.execute(
                select(HistoryChunk).where(
                    HistoryChunk.doc_id == doc_id, HistoryChunk.sealed.is_(False)
                )
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

    async def _store_payload(
        self, payload: bytes, offload: bool
    ) -> tuple[bytes | None, str | None]:
        if not offload:
            return payload, None
        key = f"{self._settings.history_blob_prefix}{uuid.uuid4().hex}"
        await self._store.put(key, payload, content_type="application/octet-stream")
        return None, key

    async def _insert_update(
        self,
        session: AsyncSession,
        *,
        chunk: HistoryChunk,
        project_id: UUID,
        doc_id: UUID,
        version: int,
        payload: bytes,
        op_count: int,
        author_id: UUID | None,
        at: datetime,
    ) -> None:
        inline, blob_key = await self._store_payload(payload, self._is_oversized(payload))
        session.add(
            HistoryUpdate(
                chunk_id=chunk.id,
                project_id=project_id,
                doc_id=doc_id,
                version=version,
                timestamp=at,
                author_id=author_id,
                payload=inline,
                payload_blob_key=blob_key,
                payload_size=len(payload),
                op_count=op_count,
            )
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)
