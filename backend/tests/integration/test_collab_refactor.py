"""Spec-30 refactor regression + invariant tests for the CRDT manager/store."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.awareness import AwarenessRegistry
from inkstave.collab.content_bridge import ContentBridge
from inkstave.collab.manager import CollabSettings, DocumentManager
from inkstave.collab.store import CrdtStore
from inkstave.collab.ydocument import YDocument
from inkstave.db.models.crdt import CrdtDocumentState
from inkstave.db.models.document import Document
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import session_factory
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _make_doc(db_session: AsyncSession, content: str = "") -> UUID:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    if content:
        await set_content_from_collab(db_session, entity.id, content)
    await db_session.flush()
    return entity.id


def _manager(db_session: AsyncSession, **over: Any) -> DocumentManager:
    factory = session_factory(db_session)
    settings = CollabSettings(
        snapshot_every_updates=over.get("snapshot_every_updates", 200),
        snapshot_interval_seconds=over.get("snapshot_interval_seconds", 30.0),
        # High debounce by default so no background flush races the shared session.
        text_flush_debounce_ms=over.get("text_flush_debounce_ms", 100_000),
        idle_evict_seconds=over.get("idle_evict_seconds", 0.02),
        max_update_bytes=over.get("max_update_bytes", 1_048_576),
    )
    return DocumentManager(
        store=CrdtStore(factory),
        content_bridge=ContentBridge(factory),
        awareness=AwarenessRegistry(),
        settings=settings,
    )


def _edit_update(open_state: bytes, new_text: str) -> bytes:
    editor = YDocument()
    editor.apply_update(open_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text(new_text)
    return collected[-1]


async def _poll(predicate: Any, attempts: int = 100, step: float = 0.01) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(step)


# --- bounded per-document maps (criterion 5) ------------------------------- #


async def test_locks_and_load_count_bounded_after_eviction(db_session: AsyncSession) -> None:
    manager = _manager(db_session, idle_evict_seconds=0.02)
    doc_ids = [await _make_doc(db_session) for _ in range(3)]
    for doc_id in doc_ids:
        await manager.acquire(doc_id)
        await manager.release(doc_id)

    await _poll(lambda: not manager._entries and not manager._locks)
    assert manager._entries == {}
    assert manager._locks == {}  # the per-document lock map does not grow unbounded
    assert manager.load_count == {}


# --- refcount + eviction invariants (criterion 4) -------------------------- #


async def test_refcount_never_negative(db_session: AsyncSession) -> None:
    manager = _manager(db_session)
    doc_id = await _make_doc(db_session)
    await manager.release(doc_id)  # never acquired -> no-op, no crash
    await manager.acquire(doc_id)
    await manager.release(doc_id)
    await manager.release(doc_id)  # double release
    entry = manager._entries.get(doc_id)
    assert entry is None or entry.refcount == 0


async def test_no_eviction_while_connections_remain(db_session: AsyncSession) -> None:
    manager = _manager(db_session, idle_evict_seconds=0.02)
    doc_id = await _make_doc(db_session)
    await manager.acquire(doc_id)
    await manager.acquire(doc_id)  # refcount 2
    await manager.release(doc_id)  # refcount 1 -> no eviction scheduled
    await asyncio.sleep(0.1)  # well past the idle window
    assert doc_id in manager._entries
    assert manager._entries[doc_id].refcount == 1


async def test_concurrent_acquire_evicted_lock_swap_loads_once(
    db_session: AsyncSession,
) -> None:
    """F-001 swap race (manager.py:123): when idle eviction pops a document's lock
    out from under a waiting acquire, the identity-mismatch retry must re-acquire on
    the fresh lock and still load the document exactly once.

    Construction (deterministic, barrier-driven): we drive an eviction that holds the
    per-document lock and then *parks inside the critical section* before popping the
    entry/lock. A concurrent ``acquire`` then blocks waiting on that very lock. When
    we release the barrier, eviction pops the entry + lock and exits; the parked
    acquire wakes on the now-orphaned lock, sees ``self._locks.get(id) is not lock``,
    and retries on the fresh lock — loading the document exactly once across the
    whole race (and never twice)."""
    manager = _manager(db_session)
    doc_id = await _make_doc(db_session, content="x")

    in_eviction = asyncio.Event()  # set once eviction holds the lock and is parked
    let_eviction_finish = asyncio.Event()  # release the parked eviction

    async def _hand_rolled_evict(document_id: UUID) -> None:
        # Mirror DocumentManager._evict_after_idle, but park (still holding the lock)
        # so a concurrent acquire is forced to wait on this exact lock object.
        lock = manager._lock(document_id)
        async with lock:
            entry = manager._entries.get(document_id)
            if entry is None or entry.refcount > 0:
                return
            in_eviction.set()
            await let_eviction_finish.wait()
            manager._entries.pop(document_id, None)
            manager._aw.drop(document_id)
            manager.load_count.pop(document_id, None)
            if manager._locks.get(document_id) is lock:
                manager._locks.pop(document_id, None)

    await manager.acquire(doc_id)  # load_count[doc] == 1
    assert manager.load_count[doc_id] == 1

    # Kick off the controlled eviction directly (refcount is currently 1, so we drop
    # it to 0 inside the task's view by releasing first).
    await manager.release(doc_id)  # refcount 0
    evict = asyncio.create_task(_hand_rolled_evict(doc_id))
    await in_eviction.wait()  # eviction now owns the lock, parked before the pop

    # This acquire wants the SAME lock eviction holds → it blocks on it.
    acquire = asyncio.create_task(manager.acquire(doc_id))
    await asyncio.sleep(0)  # ensure the acquire is parked on the lock

    let_eviction_finish.set()  # eviction pops the entry + swaps the lock, then exits
    await evict
    acquired = await acquire  # wakes on the orphaned lock → identity mismatch → retry

    assert manager.load_count[doc_id] == 1  # exactly one load across the swap race
    assert manager._entries[doc_id].refcount == 1
    assert acquired.document_id == doc_id
    await manager.release(doc_id)


# --- convergence under reordered delivery (criterion 4) -------------------- #


async def test_reordered_updates_converge_through_manager(db_session: AsyncSession) -> None:
    """AC4: delivering the same set of concurrent updates in two different orders
    through ``DocumentManager.handle_update`` converges to the same final state.

    Two clients fork from a *shared* base and each make an independent insert; we
    replay the **same** update bytes against two manager-backed docs in opposite
    orders and assert both docs reach an identical final text (CRDT commutativity
    end-to-end through the manager's apply+persist path, not just the bare
    YDocument). The docs are seeded empty and synced to one shared base first so the
    forked updates apply cleanly to both."""
    doc_a = await _make_doc(db_session)
    doc_b = await _make_doc(db_session)
    manager = _manager(db_session, text_flush_debounce_ms=100_000)

    handle_a = await manager.acquire(doc_a)
    handle_b = await manager.acquire(doc_b)

    # A single shared base both docs are synced to (identical CRDT identity), so the
    # same update bytes can be delivered to either doc.
    base = YDocument()
    base.replace_text("hello")
    base_state = base.get_state()
    base_sv = base.get_state_vector()
    await manager.handle_update(doc_a, base.diff(handle_a.ydoc.get_state_vector()), origin="base")
    await manager.handle_update(doc_b, base.diff(handle_b.ydoc.get_state_vector()), origin="base")

    # Two independent concurrent edits forked from that same base (commuting inserts).
    fork_1 = YDocument()
    fork_1.apply_update(base_state)
    fork_1._text.insert(5, " world")  # type: ignore[attr-defined]
    update_1 = fork_1.diff(base_sv)

    fork_2 = YDocument()
    fork_2.apply_update(base_state)
    fork_2._text.insert(0, "hi ")  # type: ignore[attr-defined]
    update_2 = fork_2.diff(base_sv)

    # Deliver the same update bytes in opposite orders to the two docs.
    await manager.handle_update(doc_a, update_1, origin="c1")
    await manager.handle_update(doc_a, update_2, origin="c2")
    await manager.handle_update(doc_b, update_2, origin="c2")
    await manager.handle_update(doc_b, update_1, origin="c1")

    # Both docs converge to the same final text regardless of delivery order. (We
    # compare text rather than raw state vectors: each manager doc carries its own
    # local client id from seed-on-load, so the SVs differ even though the shared
    # content has fully converged — text equality is the convergence invariant.)
    assert handle_a.text == handle_b.text  # converged regardless of delivery order
    assert handle_a.text == "hi hello world"  # the deterministic CRDT merge of both inserts


# --- persistence integrity (criterion 7) ----------------------------------- #


async def test_text_synced_seq_is_maintained(db_session: AsyncSession) -> None:
    manager = _manager(db_session)
    doc_id = await _make_doc(db_session, content="hi")
    handle = await manager.acquire(doc_id)

    before = await db_session.get(CrdtDocumentState, doc_id)
    assert before is not None and before.text_synced_seq == 0  # dead before the fix

    await manager.handle_update(doc_id, _edit_update(handle.ydoc.get_state(), "hi there"), "c")
    await manager.flush(doc_id)

    await db_session.refresh(before)
    assert before.text_synced_seq >= 1  # now tracks the flushed seq


async def test_flush_on_release_persists_final_edit(db_session: AsyncSession) -> None:
    manager = _manager(db_session, text_flush_debounce_ms=100_000)  # no background flush
    doc_id = await _make_doc(db_session, content="")
    handle = await manager.acquire(doc_id)
    await manager.handle_update(doc_id, _edit_update(handle.ydoc.get_state(), "final edit"), "c")
    await manager.release(doc_id)  # the close path must flush the final edit

    content = await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id))
    assert content == "final edit"


async def test_compaction_boundary_load_is_exact(db_session: AsyncSession) -> None:
    store = CrdtStore(session_factory(db_session))
    doc_id = await _make_doc(db_session)

    editor = YDocument()
    ups: list[bytes] = []
    editor.observe(lambda update, _origin: ups.append(update))
    for text in ("a", "ab", "abc", "abcd", "abcde"):
        editor.replace_text(text)
    ids = [await store.append_update(doc_id, u, None) for u in ups]

    # Snapshot the state up to the 2nd update and truncate <= that id.
    partial = YDocument()
    for u in ups[:2]:
        partial.apply_update(u)
    await store.snapshot(
        document_id=doc_id,
        state=partial.get_state(),
        state_vector=partial.get_state_vector(),
        upto_update_id=ids[1],
    )

    state, _seq = await store.load(doc_id)
    assert state is not None
    rebuilt = YDocument()
    rebuilt.apply_update(state)
    # The boundary update is in the snapshot (not double-applied); the rest replay.
    assert rebuilt.text == "abcde"
