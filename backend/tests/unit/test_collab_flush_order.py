"""Forced text flushes reach the spec-13 bridge in the order they copied the text (regression).

The write used to run after the per-document lock was released. A slow write of an older copy could then land
after a newer one, and ``documents.content`` (read by the agent and the compile) kept the stale text. Fakes stand
in for the store and the bridge, as in ``test_collab_debounced_flush``.
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
    async def load(self, document_id: UUID) -> tuple[bytes | None, int]:
        return None, 0

    async def max_update_id(self, document_id: UUID) -> int:
        return 0

    async def append_update(self, document_id: UUID, update: bytes, origin: str | None) -> int:
        return 1

    async def snapshot(self, **_: Any) -> int:
        return 0

    async def mark_text_synced(self, document_id: UUID, seq: int) -> None:
        return None


class _GatedBridge:
    """Records writes in the order they land; the first write waits for ``release``."""

    def __init__(self) -> None:
        self.landed: list[str] = []
        self.first_write_started = asyncio.Event()
        self.release = asyncio.Event()
        self._calls = 0

    async def load_initial_text(self, document_id: UUID) -> str:
        return ""

    async def flush_text(self, document_id: UUID, text: str) -> None:
        self._calls += 1
        if self._calls == 1:
            self.first_write_started.set()
            await self.release.wait()
        self.landed.append(text)


def _edit(open_state: bytes, text: str) -> bytes:
    editor = YDocument()
    editor.apply_update(open_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text(text)
    return collected[-1]


def _manager(bridge: _GatedBridge) -> DocumentManager:
    return DocumentManager(
        store=cast(CrdtStore, _FakeStore()),
        content_bridge=cast(ContentBridge, bridge),
        awareness=AwarenessRegistry(),
        settings=CollabSettings(text_flush_debounce_ms=60_000, idle_evict_seconds=300.0),
    )


async def test_a_newer_flush_is_not_overwritten_by_an_older_one_still_writing() -> None:
    bridge = _GatedBridge()
    manager = _manager(bridge)
    doc_id = uuid4()
    handle = await manager.acquire(doc_id)
    await manager.handle_update(doc_id, _edit(handle.ydoc.get_state(), "old"), origin="client")

    older = asyncio.create_task(manager.flush_text_now(doc_id))
    await bridge.first_write_started.wait()  # the "old" copy is being written

    # The edit and the newer flush queue behind the older write on the document lock, in that order.
    edit = asyncio.create_task(
        manager.handle_update(doc_id, _edit(handle.ydoc.get_state(), "new"), origin="client")
    )
    await asyncio.sleep(0)
    newer = asyncio.create_task(manager.flush_text_now(doc_id))
    await asyncio.sleep(0)
    bridge.release.set()
    await asyncio.gather(older, edit, newer)

    assert bridge.landed == ["old", "new"]
    await manager.aclose()


async def test_flush_text_if_dirty_writes_a_dirty_room_once_and_skips_a_clean_one() -> None:
    bridge = _GatedBridge()
    bridge.release.set()
    manager = _manager(bridge)
    doc_id = uuid4()
    handle = await manager.acquire(doc_id)

    await manager.flush_text_if_dirty(doc_id)  # nothing typed yet: no write
    assert bridge.landed == []

    await manager.handle_update(doc_id, _edit(handle.ydoc.get_state(), "typed"), origin="client")
    await manager.flush_text_if_dirty(doc_id)
    await manager.flush_text_if_dirty(doc_id)  # already written: no second write
    assert bridge.landed == ["typed"]
    await manager.aclose()
