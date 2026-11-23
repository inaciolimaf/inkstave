"""DocumentManager lock ordering without a database (spec 28, ADR 0123).

The document lock is what keeps an edit from landing between a compaction's read and its log truncation: a
compaction writes the snapshot under the lock, so an edit that arrives meanwhile waits for it. The tests here
hold the store's writes open with gates and check who gets the lock first.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import pytest

from tests.unit.collab_manager_fakes import edit_update, harness, settle


@pytest.mark.parametrize("closer", ["flush", "release"])
async def test_compaction_holds_the_document_lock_while_it_writes_the_snapshot(closer: str) -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        h.store.snapshot_gate = asyncio.Event()
        if closer == "flush":
            compacting = asyncio.create_task(h.manager.flush(doc))
        else:
            compacting = asyncio.create_task(h.manager.release(doc))
        await settle()  # the compaction is inside the store, writing the snapshot

        later = asyncio.create_task(
            h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "ab"), origin="c")
        )
        await settle()
        assert not later.done()
        assert len(h.store.appends) == 1

        h.store.snapshot_gate.set()
        await asyncio.gather(compacting, later)
        assert len(h.store.appends) == 2


@pytest.mark.parametrize("server_write", ["update", "edits"])
async def test_a_server_write_runs_after_the_updates_already_queued_on_the_lock(server_write: str) -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        seen: list[str] = []

        def plan(text: str) -> tuple[list[tuple[int, int, str]], None]:
            seen.append(text)
            return [(len(text), len(text), "!")], None

        server_call: Coroutine[Any, Any, object]
        if server_write == "update":
            server_call = h.manager.apply_server_update(doc, "restored", "restore")
        else:
            server_call = h.manager.apply_server_edits(doc, plan, origin="restore")
        lock = h.manager._lock(doc)
        await lock.acquire()
        server = asyncio.create_task(server_call)  # queues first
        await settle()
        client = asyncio.create_task(
            h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "typed"), origin="client")
        )
        await settle()  # queues behind the server write

        lock.release()
        await asyncio.gather(server, client)

        assert [origin for _, _, origin in h.store.appends] == ["client", "restore"]
        if server_write == "edits":
            assert seen == ["typed"]


async def test_release_leaves_the_document_alone_when_a_holder_arrives_during_its_flush() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        h.store.flush_gate = asyncio.Event()
        releasing = asyncio.create_task(h.manager.release(doc))
        await settle()  # the release is inside its flush, holding the lock
        arriving = asyncio.create_task(h.manager.acquire(doc))
        await settle()  # the new holder queues behind the flush

        h.store.flush_gate.set()
        await asyncio.gather(releasing, arriving)

        entry = h.manager._entries[doc]
        assert entry.refcount == 1
        assert entry.evict_task is None
        assert h.store.snapshots == []


async def test_release_returns_quietly_when_the_idle_timer_evicted_the_document_meanwhile() -> None:
    async with harness(idle_evict_seconds=0.0) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        await h.manager.release(doc)  # idle: the eviction timer is set, 0 s
        h.store.flush_gate = asyncio.Event()
        second_release = asyncio.create_task(h.manager.release(doc))
        await settle()  # the timer queues on the lock behind this release's flush

        h.store.flush_gate.set()
        await second_release

        assert h.manager.active_document_ids() == set()
        assert h.awareness.dropped == [doc]
