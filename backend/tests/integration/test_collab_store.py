"""Integration tests for CrdtStore: load order, compaction, append O(1) (spec 28)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pycrdt import Doc, Map, Text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.models import CrdtUpdate
from inkstave.modules.collab.rooms.store import CrdtStore
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _factory(db_session: AsyncSession) -> Any:
    return lambda: _SessionCtx(db_session)


async def _make_doc(db_session: AsyncSession) -> UUID:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await db_session.flush()
    return entity.id


def _updates(base_state: bytes, texts: list[str]) -> list[bytes]:
    editor = YDocument()
    editor.apply_update(base_state)
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    for text in texts:
        editor.replace_text(text)
    return collected


async def test_load_rebuilds_snapshot_then_ordered_log(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session)
    store = CrdtStore(_factory(db_session))

    base = YDocument()
    base.replace_text("A")
    await store.snapshot(
        document_id=doc_id,
        state=base.get_state(),
        state_vector=base.get_state_vector(),
        upto_update_id=None,
    )
    for update in _updates(base.get_state(), ["AB", "ABC", "ABCD"]):
        await store.append_update(doc_id, update, None)

    state, _seq = await store.load(doc_id)
    assert state is not None
    rebuilt = YDocument()
    rebuilt.apply_update(state)
    assert rebuilt.text == "ABCD"


async def test_load_none_for_unknown_document(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session)
    state, seq = await CrdtStore(_factory(db_session)).load(doc_id)
    assert state is None
    assert seq == 0


async def test_compaction_truncates_log_and_preserves_text(db_session: AsyncSession) -> None:
    doc_id = await _make_doc(db_session)
    store = CrdtStore(_factory(db_session))

    editor = YDocument()
    collected: list[bytes] = []
    editor.observe(lambda update, _origin: collected.append(update))
    editor.replace_text("Hello")
    editor.replace_text("Hello World")
    last_id = 0
    for update in collected:
        last_id = await store.append_update(doc_id, update, None)

    new_seq = await store.snapshot(
        document_id=doc_id,
        state=editor.get_state(),
        state_vector=editor.get_state_vector(),
        upto_update_id=last_id,
    )
    assert new_seq >= 1

    remaining = await db_session.scalar(
        select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == doc_id)
    )
    assert remaining == 0  # rows <= last_id were deleted

    state, seq = await store.load(doc_id)
    assert state is not None
    rebuilt = YDocument()
    rebuilt.apply_update(state)
    assert rebuilt.text == "Hello World"
    assert seq == new_seq


async def test_append_is_constant_cost(db_session: AsyncSession, query_counter: dict[str, int]) -> None:
    doc_id = await _make_doc(db_session)
    store = CrdtStore(_factory(db_session))
    update = _updates(YDocument().get_state(), ["x"])[0]

    before = query_counter["count"]
    await store.append_update(doc_id, update, None)
    first = query_counter["count"] - before

    for _ in range(5):  # grow the log
        await store.append_update(doc_id, update, None)

    before2 = query_counter["count"]
    await store.append_update(doc_id, update, None)
    later = query_counter["count"] - before2

    assert first == later == 1  # one INSERT, never reading the existing log


def _suggesting_client_updates() -> list[bytes]:
    """Updates from a client that typed a suggested insertion and a suggested deletion (spec 119)."""
    client = Doc()
    client_text = client.get(YDocument.TEXT_KEY, type=Text)
    client_map = client.get(YDocument.SUGGESTIONS_KEY, type=Map)
    collected: list[bytes] = []
    client.observe(lambda event: collected.append(event.update))
    with client.transaction():
        client_text.insert(0, "very important")
        client_map["s-insert"] = {
            "kind": "insert",
            "author_id": "u1",
            "author_name": "B",
            "created_at": "2026-11-04T10:00:00Z",
            "start": "AAE=",
            "end": "AAE=",
        }
    with client.transaction():
        client_map["s-delete"] = {
            "kind": "delete",
            "author_id": "u1",
            "author_name": "B",
            "created_at": "2026-11-04T10:01:00Z",
            "at": "AAE=",
            "text": "old",
        }
    return collected


async def test_suggestions_map_survives_compaction(db_session: AsyncSession) -> None:
    """The suggestions map (spec 119) is a second root type of the same Y.Doc: snapshot and reload keep it."""
    doc_id = await _make_doc(db_session)
    store = CrdtStore(_factory(db_session))
    collected = _suggesting_client_updates()
    last_id = 0
    for update in collected:
        last_id = await store.append_update(doc_id, update, None)

    server = YDocument()
    for update in collected:
        server.apply_update(update)
    await store.snapshot(
        document_id=doc_id,
        state=server.get_state(),
        state_vector=server.get_state_vector(),
        upto_update_id=last_id,
    )

    state, _seq = await store.load(doc_id)
    assert state is not None
    reloaded = YDocument()
    reloaded.apply_update(state)
    assert reloaded.text == "very important"
    assert set(reloaded.suggestions()) == {"s-insert", "s-delete"}
    assert reloaded.suggestions()["s-delete"]["text"] == "old"
