"""DocumentManager reads, presence and shutdown without a database: the sync answer to a client, the awareness
relay, the live text for the restore and export readers, and the cancellation of background timers.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from inkstave.modules.collab.crdt.protocol import SyncStep1, SyncStep2, read_message
from inkstave.modules.collab.crdt.ydocument import YDocument
from tests.unit.collab_manager_fakes import edit_update, harness, settle, text_state


async def test_sync_step1_answers_with_the_missing_state_and_our_state_vector() -> None:
    async with harness(stored=text_state("server text")) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)

        step2, step1 = await h.manager.handle_sync_step1(doc, YDocument().get_state_vector())

        sent = read_message(step2)
        assert isinstance(sent, SyncStep2)
        replay = YDocument()
        replay.apply_update(sent.update)
        assert replay.text == "server text"
        answer = read_message(step1)
        assert answer == SyncStep1(state_vector=handle.ydoc.get_state_vector())


async def test_sync_step1_sends_only_what_the_client_lacks() -> None:
    async with harness(stored=text_state("server text")) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        client = YDocument()
        client.apply_update(handle.ydoc.get_state())

        step2, _ = await h.manager.handle_sync_step1(doc, client.get_state_vector())

        sent = read_message(step2)
        assert isinstance(sent, SyncStep2)
        assert sent.update == handle.ydoc.diff(client.get_state_vector())


async def test_sync_step1_of_an_unacquired_document_is_a_key_error() -> None:
    async with harness() as h:
        with pytest.raises(KeyError):
            await h.manager.handle_sync_step1(uuid4(), YDocument().get_state_vector())


async def test_awareness_is_merged_through_the_registry_and_its_relay_returned() -> None:
    async with harness() as h:
        doc = uuid4()

        relay = await h.manager.handle_awareness(doc, b"presence")

        assert relay == b"relay:presence"
        assert h.awareness.applied == [(doc, b"presence")]


async def test_current_text_loads_an_idle_document_and_leaves_it_idle() -> None:
    async with harness(stored=text_state("stored")) as h:
        doc = uuid4()

        assert await h.manager.current_text(doc) == "stored"

        assert h.store.loads == [(doc, True)]
        assert h.manager._entries[doc].refcount == 0
        assert h.manager._entries[doc].evict_task is not None


async def test_aclose_cancels_the_pending_flush_and_eviction_timers_without_raising() -> None:
    async with harness() as h:
        typing_doc, idle_doc = uuid4(), uuid4()
        handle = await h.manager.acquire(typing_doc)
        await h.manager.handle_update(typing_doc, edit_update(handle.ydoc.get_state(), "typed"), origin="c")
        await h.manager.acquire(idle_doc)
        await h.manager.release(idle_doc)
        flush_timer = h.manager._entries[typing_doc].flush_task
        evict_timer = h.manager._entries[idle_doc].evict_task
        assert flush_timer is not None and evict_timer is not None

        await h.manager.aclose()

        assert flush_timer.done() and evict_timer.done()
        assert h.manager._entries[typing_doc].flush_task is None
        assert h.manager._entries[idle_doc].evict_task is None


async def test_aclose_does_not_fail_on_a_background_task_that_raises_when_cancelled() -> None:
    async def fails_on_cancel() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError as error:
            raise RuntimeError("background failure") from error

    async with harness() as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        h.manager._entries[doc].flush_task = asyncio.create_task(fails_on_cancel())
        await settle()  # the task reaches its sleep, so the cancel reaches its handler

        await h.manager.aclose()

        assert h.manager._entries[doc].flush_task is None
