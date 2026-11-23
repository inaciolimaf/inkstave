"""Fakes for the DocumentManager unit tests (``collab/rooms/manager.py``).

The store, the bridge and the awareness registry record every call, so a test can assert the exact document
id, origin and flag each call received. No database and no Redis: the tests run in the mutation selection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from inkstave.modules.collab.crdt.awareness import AwarenessRegistry
from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.rooms.content_bridge import ContentBridge
from inkstave.modules.collab.rooms.manager import CollabSettings, DocumentManager
from inkstave.modules.collab.rooms.store import CrdtStore


def text_state(text: str) -> bytes:
    """The full state of a document whose shared text is ``text``."""
    document = YDocument()
    document.replace_text(text)
    return document.get_state()


def text_of(state: bytes) -> str:
    """The shared text a full state encodes."""
    document = YDocument()
    document.apply_update(state)
    return document.text


def edit_update(open_state: bytes, text: str) -> bytes:
    """The update a client produces when it sets the text to ``text`` starting from ``open_state``."""
    client = YDocument()
    client.apply_update(open_state)
    collected: list[bytes] = []
    client.observe(lambda update, _origin: collected.append(update))
    client.replace_text(text)
    return collected[-1]


def _document(document_id: object) -> UUID:
    """The store is only ever called with a document id: a None here is a bug, not a test value."""
    if not isinstance(document_id, UUID):
        raise TypeError(f"the store was called with {document_id!r}, not a document id")
    return document_id


async def settle() -> None:
    """Let every ready task take a few steps, so a task waiting on a lock has queued on it."""
    for _ in range(3):
        await asyncio.sleep(0)


class RecordingStore:
    """Stands in for ``CrdtStore``: keeps one stored state and records every call."""

    def __init__(self, stored: bytes | None, seq: int) -> None:
        self.stored = stored
        self.seq = seq
        self.flush_result: bytes | None = None  # the merged state a flush hands back
        self.flush_seq = 3
        self.snapshot_seq = 7
        self.load_gate: asyncio.Event | None = None  # when set, the call waits for it
        self.snapshot_gate: asyncio.Event | None = None
        self.flush_gate: asyncio.Event | None = None
        self.loads: list[tuple[UUID, bool]] = []
        self.appends: list[tuple[UUID, bytes, str | None]] = []
        self.snapshots: list[tuple[UUID, bytes, int | None]] = []
        self.flushes: list[tuple[UUID, bytes | None]] = []

    async def load(self, document_id: UUID, *, seed: bool = False) -> tuple[bytes | None, int]:
        self.loads.append((_document(document_id), seed))
        if self.load_gate is not None:
            await self.load_gate.wait()
        return self.stored, self.seq

    async def append_update(self, document_id: UUID, update: bytes, origin: str | None) -> int:
        self.appends.append((_document(document_id), update, origin))
        return len(self.appends)

    async def snapshot(self, *, document_id: UUID, state: bytes, upto_update_id: int | None) -> int:
        self.snapshots.append((_document(document_id), state, upto_update_id))
        if self.snapshot_gate is not None:
            await self.snapshot_gate.wait()
        return self.snapshot_seq

    async def flush_text(
        self, document_id: UUID, memory_state: bytes | None, write_text: Any
    ) -> tuple[bytes | None, int]:
        self.flushes.append((_document(document_id), memory_state))
        if self.flush_gate is not None:
            await self.flush_gate.wait()
        source = memory_state if memory_state is not None else self.stored
        await write_text(None, document_id, text_of(source) if source is not None else "")
        return self.flush_result, self.flush_seq


class RecordingBridge:
    """Stands in for ``ContentBridge``: records the text written to ``documents.content``."""

    def __init__(self) -> None:
        self.writes: list[tuple[UUID, str]] = []

    async def write_text(self, session: object, document_id: UUID, text: str) -> None:
        self.writes.append((document_id, text))

    @property
    def texts(self) -> list[str]:
        return [text for _, text in self.writes]


class RecordingAwareness:
    """Stands in for ``AwarenessRegistry``: records the presence calls."""

    def __init__(self) -> None:
        self.applied: list[tuple[UUID, bytes]] = []
        self.dropped: list[UUID] = []

    def apply(self, document_id: UUID, update: bytes) -> bytes:
        self.applied.append((document_id, update))
        return b"relay:" + update

    def drop(self, document_id: UUID) -> None:
        self.dropped.append(document_id)


@dataclass
class Harness:
    manager: DocumentManager
    store: RecordingStore
    bridge: RecordingBridge
    awareness: RecordingAwareness


@asynccontextmanager
async def harness(*, stored: bytes | None = None, seq: int = 0, **settings: Any) -> AsyncIterator[Harness]:
    """A manager over the recording fakes. The debounce and the idle eviction are long unless a test sets them,
    and the manager is shut down when the block ends, so no timer outlives the test."""
    store = RecordingStore(stored, seq)
    bridge = RecordingBridge()
    awareness = RecordingAwareness()
    defaults: dict[str, Any] = {"text_flush_debounce_ms": 60_000, "idle_evict_seconds": 300.0}
    manager = DocumentManager(
        store=cast(CrdtStore, store),
        content_bridge=cast(ContentBridge, bridge),
        awareness=cast(AwarenessRegistry, awareness),
        settings=CollabSettings(**{**defaults, **settings}),
    )
    try:
        yield Harness(manager, store, bridge, awareness)
    finally:
        await manager.aclose()
