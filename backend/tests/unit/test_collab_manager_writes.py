"""DocumentManager write paths without a database: client updates, server edits, remote updates, flushes
and compaction (spec 28, spec 121 for server edits, ADR 0123 for replicas).

The rule each test pins is the one a lost or duplicated edit would break: an update is applied, stored and
relayed exactly once; the text reaches ``documents.content`` in order; compaction keeps what another replica
stored.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.rooms.manager import REMOTE_ORIGIN, UpdateTooLargeError
from tests.unit.collab_manager_fakes import edit_update, harness, text_state


async def test_handle_update_applies_stores_and_returns_the_update_with_its_origin() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        origins: list[str | None] = []
        handle.ydoc.observe(lambda _update, origin: origins.append(origin))
        update = edit_update(handle.ydoc.get_state(), "typed")

        relayed = await h.manager.handle_update(doc, update, origin="client-1")

        assert relayed == update
        assert h.store.appends == [(doc, update, "client-1")]
        assert origins == ["client-1"]
        assert handle.text == "typed"


async def test_handle_update_refuses_an_update_over_the_limit_and_accepts_one_at_it() -> None:
    update = edit_update(YDocument().get_state(), "typed")
    async with harness(max_update_bytes=len(update)) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        assert await h.manager.handle_update(doc, update, origin=None) == update

    async with harness(max_update_bytes=len(update) - 1) as h:
        doc = uuid4()
        await h.manager.acquire(doc)
        with pytest.raises(UpdateTooLargeError) as refused:
            await h.manager.handle_update(doc, update, origin=None)
        assert refused.value.size == len(update)
        assert refused.value.limit == len(update) - 1
        assert h.store.appends == []


async def test_the_update_counter_compacts_at_the_threshold_and_starts_again() -> None:
    async with harness(snapshot_every_updates=2) as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)  # held, so the last release does not compact
        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "a"), origin="c")
        assert h.store.snapshots == []

        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "ab"), origin="c")
        assert len(h.store.snapshots) == 1
        assert h.store.snapshots[0][0] == doc
        assert h.manager._entries[doc].updates_since_snapshot == 0

        await h.manager.handle_update(doc, edit_update(handle.ydoc.get_state(), "abc"), origin="c")
        assert len(h.store.snapshots) == 1


async def test_apply_server_update_replaces_the_text_as_one_persisted_update() -> None:
    stored = text_state("old")  # one state, so every copy shares the same item ids
    async with harness(stored=stored) as h:
        doc = uuid4()

        update = await h.manager.apply_server_update(doc, "restored", "restore-1")

        assert h.store.appends == [(doc, update, "restore-1")]
        replay = YDocument()
        replay.apply_update(stored)
        replay.apply_update(update)
        assert replay.text == "restored"
        assert h.manager._entries[doc].refcount == 0
        assert h.manager._entries[doc].evict_task is not None
        assert await h.manager.current_text(doc) == "restored"


async def test_apply_server_update_on_a_held_document_compacts_at_the_threshold_and_flushes_when_dirty() -> (
    None
):
    async with harness(snapshot_every_updates=2) as h:
        doc = uuid4()
        await h.manager.acquire(doc)

        await h.manager.apply_server_update(doc, "one", "restore-1")
        assert h.store.snapshots == []  # one update is below the threshold
        assert h.manager._entries[doc].flush_task is not None  # the write schedules a flush

        await h.manager.apply_server_update(doc, "two", "restore-2")
        assert len(h.store.snapshots) == 1
        assert h.manager._entries[doc].refcount == 1

        await h.manager.flush_text_if_dirty(doc)
        assert h.bridge.texts == ["two"]


async def test_apply_server_edits_hands_the_live_text_to_the_plan_and_applies_its_edits() -> None:
    async with harness(stored=text_state("hello world")) as h:
        doc = uuid4()
        seen: list[str] = []

        def plan(text: str) -> tuple[list[tuple[int, int, str]], str]:
            seen.append(text)
            return [(0, 5, "HELLO")], "outcome"

        update, outcome = await h.manager.apply_server_edits(doc, plan, origin="git-push")

        assert seen == ["hello world"]
        assert outcome == "outcome"
        assert update != b""
        assert h.store.appends == [(doc, update, "git-push")]
        assert h.manager._entries[doc].refcount == 0
        assert await h.manager.current_text(doc) == "HELLO world"


async def test_apply_server_edits_with_nothing_to_change_appends_nothing() -> None:
    async with harness(stored=text_state("same")) as h:
        doc = uuid4()

        update, outcome = await h.manager.apply_server_edits(
            doc, lambda _text: ([], "unchanged"), origin="git-push"
        )

        assert update == b""
        assert outcome == "unchanged"
        assert h.store.appends == []
        assert h.manager._entries[doc].refcount == 0
        assert await h.manager.current_text(doc) == "same"


async def test_apply_server_edits_on_a_held_document_counts_and_flushes_when_dirty() -> None:
    async with harness(snapshot_every_updates=2) as h:
        doc = uuid4()
        await h.manager.acquire(doc)

        def append_bang(text: str) -> tuple[list[tuple[int, int, str]], None]:
            return [(len(text), len(text), "!")], None

        await h.manager.apply_server_edits(doc, append_bang, origin="git-push")
        assert h.store.snapshots == []
        assert h.manager._entries[doc].flush_task is not None
        await h.manager.apply_server_edits(doc, append_bang, origin="git-push")
        assert len(h.store.snapshots) == 1

        await h.manager.flush_text_if_dirty(doc)
        assert h.bridge.texts == ["!!"]


async def test_a_remote_update_is_applied_locally_without_storing_or_echoing_it() -> None:
    async with harness() as h:
        doc = uuid4()
        handle = await h.manager.acquire(doc)
        origins: list[str | None] = []
        handle.ydoc.observe(lambda _update, origin: origins.append(origin))
        update = edit_update(handle.ydoc.get_state(), "remote")

        await h.manager.apply_remote_update(doc, update)

        assert handle.text == "remote"
        assert origins == [REMOTE_ORIGIN]
        assert h.store.appends == []
        assert h.manager._entries[doc].flush_task is not None
        await h.manager.flush_text_if_dirty(doc)
        assert h.bridge.texts == ["remote"]


async def test_a_remote_update_for_a_document_not_open_here_is_ignored() -> None:
    async with harness() as h:
        await h.manager.apply_remote_update(uuid4(), b"not applied")

        assert h.store.appends == []
        assert h.store.flushes == []
