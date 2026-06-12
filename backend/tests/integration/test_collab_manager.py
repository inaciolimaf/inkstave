"""Integration tests for DocumentManager + ContentBridge (spec 28)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.awareness import AwarenessRegistry
from inkstave.collab.content_bridge import ContentBridge
from inkstave.collab.manager import CollabSettings, DocumentManager, UpdateTooLarge
from inkstave.collab.store import CrdtStore
from inkstave.collab.ydocument import YDocument
from inkstave.db.models.crdt import CrdtDocumentState, CrdtUpdate
from inkstave.db.models.document import Document
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

# Managers created via ``_manager`` in a test, so an autouse fixture can cancel
# their debounced flush/evict tasks before the db_session connection is closed —
# otherwise a late task wakes against a dead connection (spec-55 de-flake).
_created_managers: list[DocumentManager] = []


@pytest_asyncio.fixture(autouse=True)
async def _close_managers(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    while _created_managers:
        await _created_managers.pop().aclose()


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _factory(db_session: AsyncSession) -> Any:
    return lambda: _SessionCtx(db_session)


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
    factory = _factory(db_session)
    # Default to debounces that NEVER fire on their own during a test: the shared
    # db_session is a single asyncpg connection that can't service a background
    # flush/evict task concurrently with the test body (or be rolled back while one
    # runs). Tests drive flushing explicitly via ``manager.flush()``; tests that
    # exercise eviction override ``idle_evict_seconds``. This removes the spec-55
    # teardown race at its root rather than racing the debounce timer.
    settings = CollabSettings(
        snapshot_every_updates=over.get("snapshot_every_updates", 200),
        snapshot_interval_seconds=over.get("snapshot_interval_seconds", 30.0),
        text_flush_debounce_ms=over.get("text_flush_debounce_ms", 100_000),
        idle_evict_seconds=over.get("idle_evict_seconds", 300.0),
        max_update_bytes=over.get("max_update_bytes", 1_048_576),
    )
    manager = DocumentManager(
        store=CrdtStore(factory),
        content_bridge=ContentBridge(factory),
        awareness=AwarenessRegistry(),
        settings=settings,
    )
    _created_managers.append(manager)
    return manager


def _edit_update(open_state: bytes, new_text: str) -> bytes:
    editor = YDocument()
    editor.apply_update(open_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text(new_text)
    return collected[-1]


async def _content(db_session: AsyncSession, doc_id: UUID) -> str:
    return (
        await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id))
    ) or ""


async def test_seeds_crdt_from_spec13_content(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="Seed")
    manager = _manager(db_session)
    handle = await manager.acquire(doc_id)
    assert handle.text == "Seed"


async def test_flush_bridges_text_to_spec13(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="Hello")
    manager = _manager(db_session)
    handle = await manager.acquire(doc_id)

    update = _edit_update(handle.ydoc.get_state(), "Hello World")
    await manager.handle_update(doc_id, update, origin="client-1")
    await manager.flush(doc_id)

    assert handle.text == "Hello World"
    assert await _content(db_session, doc_id) == "Hello World"


async def test_bridge_write_does_not_create_crdt_update(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="Hello")
    manager = _manager(db_session)
    handle = await manager.acquire(doc_id)

    update = _edit_update(handle.ydoc.get_state(), "Hello!")
    await manager.handle_update(doc_id, update, origin="c")
    before = await db_session.scalar(
        select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == doc_id)
    )

    # A direct bridge write (the spec-13 sync) must NOT emit a CRDT update — no loop.
    await ContentBridge(_factory(db_session)).flush_text(doc_id, "Hello!")
    after = await db_session.scalar(
        select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == doc_id)
    )
    assert before == after == 1
    assert await _content(db_session, doc_id) == "Hello!"


async def test_concurrent_acquire_loads_once(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="x")
    manager = _manager(db_session)
    await asyncio.gather(manager.acquire(doc_id), manager.acquire(doc_id))
    assert manager.load_count[doc_id] == 1
    assert manager._entries[doc_id].refcount == 2


async def test_inline_compaction_fires_after_count(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 28 §5.2.5: handle_update → _maybe_compact → _compact fires once the
    update count reaches ``snapshot_every_updates`` (exercised at the manager
    layer, not just via the default 200)."""
    doc_id = await _make_doc(db_session, content="Seed")
    manager = _manager(db_session, snapshot_every_updates=1)
    handle = await manager.acquire(doc_id)

    compacted: list[UUID] = []
    original = manager._compact

    async def _spy(document_id: UUID, entry: Any) -> None:
        compacted.append(document_id)
        await original(document_id, entry)

    monkeypatch.setattr(manager, "_compact", _spy)

    # The seed-on-load already snapshotted; capture the current seq so we can
    # assert the count-based compaction bumps it again.
    before_seq = await db_session.scalar(
        select(CrdtDocumentState.seq).where(CrdtDocumentState.document_id == doc_id)
    )
    update = _edit_update(handle.ydoc.get_state(), "Seed!")
    await manager.handle_update(doc_id, update, origin="c")

    assert compacted == [doc_id]  # _compact fired via the count-based trigger
    after_seq = await db_session.scalar(
        select(CrdtDocumentState.seq).where(CrdtDocumentState.document_id == doc_id)
    )
    assert after_seq is not None and before_seq is not None and after_seq > before_seq


async def test_idle_eviction_after_release(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="x")
    manager = _manager(db_session, idle_evict_seconds=0.02)
    await manager.acquire(doc_id)
    await manager.acquire(doc_id)
    await manager.release(doc_id)
    await manager.release(doc_id)
    assert doc_id in manager._entries  # still present during the grace period
    # Poll for eviction (robust against event-loop load under the full suite).
    for _ in range(100):
        await asyncio.sleep(0.01)
        if doc_id not in manager._entries:
            break
    assert doc_id not in manager._entries  # evicted; memory does not grow


async def test_update_size_guard(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session, content="x")
    manager = _manager(db_session, max_update_bytes=10)
    await manager.acquire(doc_id)
    with pytest.raises(UpdateTooLarge):
        await manager.handle_update(doc_id, b"x" * 50, origin=None)


async def test_sync_step1_returns_two_messages(db_session: AsyncSession) -> None:
    from inkstave.collab.protocol import SyncStep1, SyncStep2, read_message

    doc_id = await _make_doc(db_session, content="Hello")
    manager = _manager(db_session)
    await manager.acquire(doc_id)

    empty_client = YDocument()
    step2, step1 = await manager.handle_sync_step1(doc_id, empty_client.get_state_vector())

    assert isinstance(read_message(step1), SyncStep1)
    parsed = read_message(step2)
    assert isinstance(parsed, SyncStep2)
    # The client applies the step-2 diff and converges to "Hello".
    empty_client.apply_update(parsed.update)
    assert empty_client.text == "Hello"


async def test_aclose_cancels_pending_background_tasks(db_session: AsyncSession) -> None:
    """Spec-55 de-flake: aclose() cancels debounced flush/evict tasks so none can
    wake against a closed connection (the root cause of the xdist teardown race)."""
    manager = _manager(db_session, idle_evict_seconds=100_000.0)
    doc_id = await _make_doc(db_session)
    await manager.acquire(doc_id)
    await manager.release(doc_id)  # refcount 0 → schedules a long idle-evict task

    entry = manager._entries.get(doc_id)
    assert entry is not None and entry.evict_task is not None
    assert not entry.evict_task.done()

    await manager.aclose()
    assert entry.evict_task is None  # cancelled and cleared — no task left pending
