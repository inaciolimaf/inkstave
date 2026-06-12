"""DocumentManager: the single object spec 29 drives (spec 28).

Owns in-memory ``YDocument``s keyed by document id with refcounting, lazy single
load, debounced text-bridge flushing, snapshot/compaction, and idle eviction. No
transport here — plain async methods.
"""

from __future__ import annotations

import asyncio
import contextlib
from time import monotonic
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.collab.protocol import encode_sync_step1, encode_sync_step2
from inkstave.collab.state import (
    CollabSettings,
    OpenDocument,
    UpdateTooLarge,
    _Entry,
)
from inkstave.collab.ydocument import YDocument

if TYPE_CHECKING:
    from inkstave.collab.awareness import AwarenessRegistry
    from inkstave.collab.content_bridge import ContentBridge
    from inkstave.collab.store import CrdtStore

__all__ = [
    "CollabSettings",
    "DocumentManager",
    "OpenDocument",
    "UpdateTooLarge",
]


class DocumentManager:
    def __init__(
        self,
        store: CrdtStore,
        content_bridge: ContentBridge,
        awareness: AwarenessRegistry,
        settings: CollabSettings,
    ) -> None:
        self._store = store
        self._bridge = content_bridge
        self._aw = awareness
        self._settings = settings
        self._entries: dict[UUID, _Entry] = {}
        self._locks: dict[UUID, asyncio.Lock] = {}
        self.load_count: dict[UUID, int] = {}  # test instrumentation

    def _lock(self, document_id: UUID) -> asyncio.Lock:
        lock = self._locks.get(document_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[document_id] = lock
        return lock

    def _require(self, document_id: UUID) -> _Entry:
        entry = self._entries.get(document_id)
        if entry is None:
            raise KeyError(f"document {document_id} is not acquired")
        return entry

    # --------------------------------------------------------------- lifecycle #

    async def acquire(self, document_id: UUID) -> OpenDocument:
        # Retry guards the rare race where eviction swaps out this document's lock
        # (to keep the locks map bounded) while we were waiting on the old one: the
        # identity check detects the swap and we re-acquire with the current lock,
        # so two concurrent acquires still load exactly once.
        while True:
            lock = self._lock(document_id)
            async with lock:
                if self._locks.get(document_id) is not lock:
                    continue
                entry = self._entries.get(document_id)
                if entry is None:
                    entry = await self._load(document_id)
                    self._entries[document_id] = entry
                entry.refcount += 1
                if entry.evict_task is not None:
                    entry.evict_task.cancel()
                    entry.evict_task = None
                return OpenDocument(self, document_id, entry.ydoc)

    async def _load(self, document_id: UUID) -> _Entry:
        self.load_count[document_id] = self.load_count.get(document_id, 0) + 1
        state, seq = await self._store.load(document_id)
        ydoc = YDocument()
        if state is not None:
            ydoc.apply_update(state)
        entry = _Entry(ydoc=ydoc, seq=seq)
        entry.last_update_id = await self._store.max_update_id(document_id)

        # First-ever open with empty CRDT but existing spec-13 content: seed it.
        if not ydoc.text:
            seed = await self._bridge.load_initial_text(document_id)
            if seed:
                ydoc.replace_text(seed)
                entry.seq = await self._store.snapshot(
                    document_id, ydoc.get_state(), ydoc.get_state_vector(), None
                )
                entry.last_snapshot_at = monotonic()
        return entry

    async def release(self, document_id: UUID) -> None:
        async with self._lock(document_id):
            entry = self._entries.get(document_id)
            if entry is None:
                return
            entry.refcount = max(0, entry.refcount - 1)
            if entry.refcount > 0:
                return

        # Refcount hit zero: flush text + snapshot, then schedule idle eviction.
        await self._do_flush_text(document_id, force=True)
        async with self._lock(document_id):
            entry = self._entries.get(document_id)
            if entry is None or entry.refcount > 0:
                return
            if entry.updates_since_snapshot > 0:
                await self._compact(document_id, entry)
            if entry.evict_task is not None:
                entry.evict_task.cancel()
            entry.evict_task = asyncio.create_task(self._evict_after_idle(document_id))

    async def _evict_after_idle(self, document_id: UUID) -> None:
        try:
            await asyncio.sleep(self._settings.idle_evict_seconds)
        except asyncio.CancelledError:
            return
        lock = self._lock(document_id)
        async with lock:
            entry = self._entries.get(document_id)
            if entry is None or entry.refcount > 0:
                return
            self._entries.pop(document_id, None)
            self._aw.drop(document_id)
            # Keep the per-document maps bounded: drop this document's lock (held
            # right now) and load counter. A concurrent acquire waiting on this
            # lock detects the swap (identity check) and retries with a fresh lock.
            self.load_count.pop(document_id, None)
            if self._locks.get(document_id) is lock:
                self._locks.pop(document_id, None)

    # ----------------------------------------------------------------- protocol #

    async def handle_sync_step1(
        self, document_id: UUID, state_vector: bytes
    ) -> tuple[bytes, bytes]:
        """Return ``(sync_step2_for_client, server_sync_step1)`` as encoded messages."""
        async with self._lock(document_id):
            entry = self._require(document_id)
            step2 = encode_sync_step2(entry.ydoc.diff(state_vector))
            step1 = encode_sync_step1(entry.ydoc.get_state_vector())
            return step2, step1

    async def handle_update(self, document_id: UUID, update: bytes, origin: str | None) -> bytes:
        """Apply, persist, schedule a text flush, and return the raw update to relay."""
        if len(update) > self._settings.max_update_bytes:
            raise UpdateTooLarge(len(update), self._settings.max_update_bytes)
        async with self._lock(document_id):
            entry = self._require(document_id)
            entry.ydoc.apply_update(update, origin=origin)
            new_id = await self._store.append_update(document_id, update, origin)
            entry.last_update_id = max(entry.last_update_id, new_id)
            entry.updates_since_snapshot += 1
            entry.dirty_text = True
            await self._maybe_compact(document_id, entry)
        self._schedule_flush(document_id)
        return update

    async def apply_server_update(
        self, document_id: UUID, new_text: str, origin: str | None
    ) -> bytes:
        """Apply a server-originated text replacement as one CRDT update (restore, spec 37).

        Acquires the doc (loading it if no clients are connected), replaces the shared
        text in a single transaction, persists + schedules a flush, and returns the raw
        update so the caller can broadcast it and capture it into history.
        """
        await self.acquire(document_id)
        try:
            async with self._lock(document_id):
                entry = self._require(document_id)
                update = entry.ydoc.replace_text(new_text)
                new_id = await self._store.append_update(document_id, update, origin)
                entry.last_update_id = max(entry.last_update_id, new_id)
                entry.updates_since_snapshot += 1
                entry.dirty_text = True
                await self._maybe_compact(document_id, entry)
            self._schedule_flush(document_id)
            return update
        finally:
            await self.release(document_id)

    async def current_text(self, document_id: UUID) -> str:
        """The live authoritative text (loads the doc from storage if idle)."""
        await self.acquire(document_id)
        try:
            return self._require(document_id).ydoc.text
        finally:
            await self.release(document_id)

    def active_document_ids(self) -> set[UUID]:
        """Document ids with a live in-memory room right now.

        Used to flush only the currently-open docs to ``documents.content`` before
        a worker job (agent/compile) reads that column — see ``collab.flush``.
        """
        return set(self._entries)

    async def handle_awareness(self, document_id: UUID, update: bytes) -> bytes:
        """Merge an awareness update and return the raw blob to relay (ephemeral)."""
        return self._aw.apply(document_id, update)

    # -------------------------------------------------------------- maintenance #

    def _schedule_flush(self, document_id: UUID) -> None:
        entry = self._entries.get(document_id)
        if entry is None:
            return
        if entry.flush_task is not None and not entry.flush_task.done():
            return  # a trailing flush is already scheduled within the debounce window
        delay = self._settings.text_flush_debounce_ms / 1000
        entry.flush_task = asyncio.create_task(self._delayed_flush(document_id, delay))

    async def _delayed_flush(self, document_id: UUID, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        await self._do_flush_text(document_id, force=False)

    async def _do_flush_text(self, document_id: UUID, *, force: bool) -> None:
        async with self._lock(document_id):
            entry = self._entries.get(document_id)
            if entry is None or (not force and not entry.dirty_text):
                return
            text = entry.ydoc.text
            seq = entry.seq
            entry.dirty_text = False
            if entry.flush_task is not None and not entry.flush_task.done():
                entry.flush_task.cancel()
            entry.flush_task = None
        await self._bridge.flush_text(document_id, text)
        # Record that spec-13 content is current as of this seq, so a recovered
        # process can tell its persisted text is not stale.
        await self._store.mark_text_synced(document_id, seq)

    async def _maybe_compact(self, document_id: UUID, entry: _Entry) -> None:
        by_count = entry.updates_since_snapshot >= self._settings.snapshot_every_updates
        by_time = (monotonic() - entry.last_snapshot_at) >= self._settings.snapshot_interval_seconds
        if by_count or by_time:
            await self._compact(document_id, entry)

    async def _compact(self, document_id: UUID, entry: _Entry) -> None:
        """Snapshot the current state and truncate the log up to the high-water id."""
        entry.seq = await self._store.snapshot(
            document_id,
            entry.ydoc.get_state(),
            entry.ydoc.get_state_vector(),
            entry.last_update_id,
        )
        entry.updates_since_snapshot = 0
        entry.last_snapshot_at = monotonic()

    async def flush(self, document_id: UUID) -> None:
        """Force the text bridge now, and compact if the log has grown."""
        await self._do_flush_text(document_id, force=True)
        async with self._lock(document_id):
            entry = self._entries.get(document_id)
            if entry is not None and entry.updates_since_snapshot > 0:
                await self._compact(document_id, entry)

    async def aclose(self) -> None:
        """Cancel all background flush/idle-evict tasks and await their exit.

        Called on app shutdown (and in tests) so a debounced task can never wake up
        after the DB engine/connection it uses has been disposed — the root cause of
        the spec-55 ``connection is closed`` teardown race under high xdist load.
        """
        pending: list[asyncio.Task[None]] = []
        for entry in self._entries.values():
            for task in (entry.flush_task, entry.evict_task):
                if task is not None and not task.done():
                    task.cancel()
                    pending.append(task)
            entry.flush_task = None
            entry.evict_task = None
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
