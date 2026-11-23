"""DocumentManager lifecycle without a database: acquire, release, idle eviction, loading and shutdown.

Each test pins one rule the lifecycle keeps (spec 28, ADR 0123). The recording fakes in
``collab_manager_fakes`` show a wrong document id, origin or flag in the assertion.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import uuid4

import pytest

from inkstave.modules.collab.crdt.state import OpenDocument
from inkstave.modules.collab.crdt.ydocument import YDocument
from tests.unit.collab_manager_fakes import edit_update, harness, settle, text_of, text_state


async def test_acquire_loads_the_stored_text_once_and_counts_each_holder() -> None:
    async with harness(stored=text_state("stored"), seq=5) as h:
        doc = uuid4()
        first = await h.manager.acquire(doc)
        second = await h.manager.acquire(doc)

        assert isinstance(first, OpenDocument)
        assert first.document_id == doc and second.document_id == doc
        assert first.text == "stored"
        assert h.store.loads == [(doc, True)]
        assert h.manager.load_count == {doc: 1}
        assert h.manager.active_document_ids() == {doc}
        assert h.manager._entries[doc].refcount == 2
        assert h.manager._entries[doc].seq == 5

        await first.release()
        assert h.manager._entries[doc].refcount == 1


async def test_concurrent_acquires_wait_for_one_load() -> None:
    async with harness() as h:
        h.store.load_gate = asyncio.Event()
        doc = uuid4()
        first = asyncio.create_task(h.manager.acquire(doc))
        second = asyncio.create_task(h.manager.acquire(doc))
        await settle()
        h.store.load_gate.set()
        handles = await asyncio.gather(first, second)

        assert all(isinstance(handle, OpenDocument) for handle in handles)
        assert h.store.loads == [(doc, True)]
        assert h.manager._entries[doc].refcount == 2


async def test_an_acquire_that_waited_on_an_evicted_lock_reloads_the_document_once() -> None:
    async with harness(stored=text_state("kept"), idle_evict_seconds=0.0) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)  # idle now: the eviction timer runs next
        lock = h.manager._lock(doc)
        await lock.acquire()  # the eviction queues on this lock first
        await settle()
        waiter = asyncio.create_task(h.manager.acquire(doc))  # then the acquire
        await settle()

        lock.release()
        handle = await waiter

        assert isinstance(handle, OpenDocument)
        assert handle.text == "kept"
        assert h.manager.load_count == {doc: 1}
        assert h.store.loads == [(doc, True), (doc, True)]


async def test_a_document_evicted_and_opened_again_loads_again() -> None:
    async with harness(stored=text_state("kept"), idle_evict_seconds=0.0) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)
        timer = h.manager._entries[doc].evict_task
        assert timer is not None
        await timer

        handle = await h.manager.acquire(doc)

        assert handle.text == "kept"
        assert h.manager.load_count == {doc: 1}
        assert h.store.loads == [(doc, True), (doc, True)]


async def test_release_keeps_the_document_while_another_holder_remains() -> None:
    async with harness() as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.acquire(doc)
        await h.manager.release(doc)

        entry = h.manager._entries[doc]
        assert entry.refcount == 1
        assert entry.evict_task is None
        assert h.store.flushes == []
        assert h.store.snapshots == []


async def test_the_last_release_flushes_compacts_and_schedules_eviction() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "typed"), origin="client")

        await h.manager.release(doc)

        entry = h.manager._entries[doc]
        assert entry.refcount == 0
        assert h.bridge.texts == ["typed"]
        assert len(h.store.snapshots) == 1
        snapshot_doc, snapshot_state, upto = h.store.snapshots[0]
        assert snapshot_doc == doc and upto is None
        assert text_of(snapshot_state) == "typed"
        assert entry.updates_since_snapshot == 0
        assert entry.evict_task is not None


async def test_releasing_a_clean_document_forces_a_flush_but_writes_no_snapshot() -> None:
    async with harness(stored=text_state("kept")) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)

        assert [flushed for flushed, _ in h.store.flushes] == [doc]
        assert h.bridge.texts == ["kept"]
        assert h.store.snapshots == []


async def test_release_of_an_unknown_document_does_nothing() -> None:
    async with harness() as h:
        await h.manager.release(uuid4())

        assert h.store.flushes == []
        assert h.store.snapshots == []


async def test_releasing_an_idle_document_again_replaces_its_idle_timer() -> None:
    async with harness() as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)
        first = h.manager._entries[doc].evict_task

        await h.manager.release(doc)  # the count stays at zero
        second = h.manager._entries[doc].evict_task

        assert first is not None and second is not None and second is not first
        await settle()
        assert first.done()


async def test_release_counts_down_only_while_it_holds_the_document_lock() -> None:
    async with harness() as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        lock = h.manager._lock(doc)
        await lock.acquire()

        releasing = asyncio.create_task(h.manager.release(doc))
        await settle()
        assert h.manager._entries[doc].refcount == 1

        lock.release()
        await releasing
        assert h.manager._entries[doc].refcount == 0


@pytest.mark.parametrize("operation", ["handle_update", "apply_remote_update", "handle_sync_step1"])
async def test_document_operations_wait_for_the_document_lock(operation: str) -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        update = edit_update(handle.ydoc.get_state(), "typed")
        calls: dict[str, Callable[[], Coroutine[Any, Any, object]]] = {
            "handle_update": lambda: h.manager.handle_update(doc, update, origin="client"),
            "apply_remote_update": lambda: h.manager.apply_remote_update(doc, update),
            "handle_sync_step1": lambda: h.manager.handle_sync_step1(doc, YDocument().get_state_vector()),
        }
        lock = h.manager._lock(doc)
        await lock.acquire()

        pending: asyncio.Task[object] = asyncio.create_task(calls[operation]())
        await settle()
        assert not pending.done()
        assert h.store.appends == []
        assert handle.text == ""

        lock.release()
        await pending


async def test_idle_eviction_drops_the_document_and_its_per_document_state() -> None:
    async with harness(idle_evict_seconds=0.0) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)
        timer = h.manager._entries[doc].evict_task
        assert timer is not None

        await timer

        assert h.manager.active_document_ids() == set()
        assert doc not in h.manager.load_count
        assert doc not in h.manager._locks
        assert h.awareness.dropped == [doc]


async def test_idle_eviction_keeps_a_document_held_again_and_ignores_an_unknown_one() -> None:
    async with harness(idle_evict_seconds=0.0) as h:
        doc = uuid4()
        await h.manager.acquire(doc)

        await h.manager._evict_after_idle(doc)
        await h.manager._evict_after_idle(uuid4())

        assert h.manager.active_document_ids() == {doc}
        assert h.awareness.dropped == []
