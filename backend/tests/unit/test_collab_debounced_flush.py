"""The debounced text flush of an open room reaches the spec-13 bridge (regression).

The timer task used to cancel itself: ``_do_flush_text`` cancels the scheduled ``flush_task``, and when the
timer itself is that task, the cancel lands on its own next ``await``. The text then reached
``documents.content`` only when the room closed. Fakes stand in for the store and the bridge, so the timer can
fire without a database.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID, uuid4

from inkstave.modules.collab.crdt.awareness import AwarenessRegistry
from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.rooms.content_bridge import ContentBridge
from inkstave.modules.collab.rooms.manager import CollabSettings, DocumentManager
from inkstave.modules.collab.rooms.store import CrdtStore


class _FakeStore:
    def __init__(self) -> None:
        self.synced: list[int] = []
        self._next = 0

    async def load(self, document_id: UUID) -> tuple[bytes | None, int]:
        return None, 0

    async def max_update_id(self, document_id: UUID) -> int:
        return 0

    async def append_update(self, document_id: UUID, update: bytes, origin: str | None) -> int:
        await asyncio.sleep(0)
        self._next += 1
        return self._next

    async def snapshot(self, **_: Any) -> int:
        return 0

    async def mark_text_synced(self, document_id: UUID, seq: int) -> None:
        self.synced.append(seq)


class _FakeBridge:
    def __init__(self) -> None:
        self.flushed: list[str] = []

    async def load_initial_text(self, document_id: UUID) -> str:
        return ""

    async def flush_text(self, document_id: UUID, text: str) -> None:
        await asyncio.sleep(0)  # a real write awaits the database here
        self.flushed.append(text)


def _edit(open_state: bytes, text: str) -> bytes:
    editor = YDocument()
    editor.apply_update(open_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text(text)
    return collected[-1]


async def test_the_debounced_flush_writes_the_text_while_the_room_stays_open() -> None:
    bridge = _FakeBridge()
    manager = DocumentManager(
        store=cast(CrdtStore, _FakeStore()),
        content_bridge=cast(ContentBridge, bridge),
        awareness=AwarenessRegistry(),
        settings=CollabSettings(text_flush_debounce_ms=10, idle_evict_seconds=300.0),
    )
    doc_id = uuid4()
    handle = await manager.acquire(doc_id)

    await manager.handle_update(doc_id, _edit(handle.ydoc.get_state(), "typed"), origin="client")
    await asyncio.sleep(0.1)

    assert bridge.flushed == ["typed"]
