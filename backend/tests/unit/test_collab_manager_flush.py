"""DocumentManager flushes and compaction without a database: what reaches ``documents.content`` and when the log
is folded into a snapshot (spec 28, ADR 0123). The debounce and the write-path timers are here too.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

import inkstave.modules.collab.rooms.manager as manager_module
from inkstave.modules.collab.crdt.ydocument import YDocument
from tests.unit.collab_manager_fakes import edit_update, harness, settle, text_of, text_state


async def test_compaction_by_time_happens_once_the_interval_has_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    monkeypatch.setattr(manager_module, "monotonic", lambda: clock[0])
    async with harness(snapshot_every_updates=10_000, snapshot_interval_seconds=10.0) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        h.manager._entries[doc].last_snapshot_at = 100.0

        clock[0] = 109.0
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        assert h.store.snapshots == []

        clock[0] = 110.0
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "ab"), origin="c")
        assert len(h.store.snapshots) == 1


async def test_the_debounced_flush_is_scheduled_after_the_debounce_in_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with harness(text_flush_debounce_ms=250) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        delays: list[float] = []

        async def record(_document_id: UUID, delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(h.manager, "_delayed_flush", record)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        await settle()

        assert delays == [0.25]


async def test_an_update_while_a_flush_is_pending_keeps_the_same_timer() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        timer = h.manager._entries[doc].flush_task
        assert timer is not None

        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "ab"), origin="c")

        assert h.manager._entries[doc].flush_task is timer


async def test_a_forced_flush_cancels_the_pending_debounce_timer() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "typed"), origin="c")
        timer = h.manager._entries[doc].flush_task
        assert timer is not None

        await h.manager.flush_text_now(doc)
        await settle()

        assert timer.done()
        assert h.manager._entries[doc].flush_task is None


async def test_flush_text_now_writes_a_document_with_no_pending_edit() -> None:
    async with harness(stored=text_state("kept")) as h:
        doc = uuid4()
        await h.manager.acquire(doc)

        await h.manager.flush_text_now(doc)
        assert h.bridge.texts == ["kept"]

        await h.manager.flush_text_if_dirty(doc)
        assert h.bridge.texts == ["kept"]


async def test_flush_of_an_idle_document_writes_the_stored_text_without_opening_it() -> None:
    async with harness(stored=text_state("on disk")) as h:
        doc = uuid4()

        await h.manager.flush(doc)

        assert h.store.flushes == [(doc, None)]
        assert h.bridge.texts == ["on disk"]
        assert h.manager.active_document_ids() == set()
        assert h.manager.load_count == {}


async def test_flush_of_an_open_document_compacts_only_when_the_log_has_grown() -> None:
    async with harness(stored=text_state("base")) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)

        await h.manager.flush(doc)
        assert h.store.snapshots == []
        assert h.bridge.texts == ["base"]

        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "base+"), origin="c")
        await h.manager.flush(doc)
        assert len(h.store.snapshots) == 1
        assert h.bridge.texts[-1] == "base+"


async def test_flush_takes_in_the_merged_state_and_seq_the_store_returns() -> None:
    async with harness(stored=text_state("mine")) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        remote = edit_update(handle.ydoc.get_state(), "mine and yours")
        merged = YDocument()
        merged.apply_update(handle.ydoc.get_state())
        merged.apply_update(remote)
        h.store.flush_result = merged.get_state()

        await h.manager.flush_text_now(doc)

        assert handle.text == "mine and yours"
        assert h.manager._entries[doc].seq == h.store.flush_seq


async def test_compaction_takes_in_the_update_another_replica_stored() -> None:
    async with harness(snapshot_every_updates=1) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        local = edit_update(handle.ydoc.get_state(), "local")
        remote = edit_update(handle.ydoc.get_state(), "remote")
        merged = YDocument()
        merged.apply_update(local)
        merged.apply_update(remote)
        h.store.stored = merged.get_state()  # the other replica's edit is stored, not yet relayed here

        await h.manager.handle_update(doc, local, origin="client")

        assert [text_of(state) for _, state, _ in h.store.snapshots] == ["local"]
        assert handle.text == merged.text


async def test_a_flush_waits_for_the_document_lock_before_writing() -> None:
    async with harness(stored=text_state("kept")) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        lock = h.manager._lock(doc)
        await lock.acquire()

        flushing = asyncio.create_task(h.manager.flush_text_now(doc))
        await settle()
        assert h.bridge.texts == []

        lock.release()
        await flushing
        assert h.bridge.texts == ["kept"]


async def test_document_ids_stay_distinct_across_documents() -> None:
    async with harness(stored=text_state("a")) as h:
        first, second = uuid4(), uuid4()
        await h.manager.acquire(first)
        await h.manager.acquire(second)

        await h.manager.flush(first)

        assert [doc for doc, _ in h.store.flushes] == [first]
        assert h.manager.active_document_ids() == {first, second}
