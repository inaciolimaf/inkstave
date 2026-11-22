"""Several backend replicas sharing Postgres and Redis stay safe for collaboration (ADR 0123).

Each replica is a ``CollabComponents`` with its own in-memory rooms. They share the database and
one fake Redis server, and each replica subscribes with the production forwarder, so a relayed
update reaches the other replica the way it does in production.
"""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any
from uuid import UUID

import fakeredis.aioredis as fakeredis
import pytest
from fakeredis import FakeServer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import Settings
from inkstave.modules.collab.crdt.protocol import encode_update
from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.models import CrdtUpdate
from inkstave.modules.collab.rooms.flush import flush_open_project_docs
from inkstave.modules.collab.rooms.manager import OpenDocument
from inkstave.modules.collab.rooms.store import CrdtStore
from inkstave.modules.collab.ws.components import CollabComponents, build_collab_components
from inkstave.modules.collab.ws.connection import _make_forwarder
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import set_content_from_collab
from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.collab_ws_harness import session_factory
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _Replica:
    """One backend process: its own rooms and manager, the shared database and Redis."""

    def __init__(self, name: str, db_session: AsyncSession, server: FakeServer) -> None:
        settings = Settings(_env_file=None, collab_text_flush_debounce_ms=60_000)  # no timer-driven flush
        self._redis: Any = fakeredis.FakeRedis(server=server)
        self.components: CollabComponents = build_collab_components(
            redis=self._redis,
            session_factory=session_factory(db_session),
            settings=settings,
            instance_id=name,
        )
        self._handles: dict[UUID, OpenDocument] = {}
        self._subscriptions: list[Any] = []

    async def open(self, document_id: UUID) -> None:
        """Join the document's room the way the WebSocket handler does."""
        self._handles[document_id] = await self.components.manager.acquire(document_id)
        subscription = await self.components.redis_bridge.subscribe(
            document_id, _make_forwarder(self.components, document_id)
        )
        self._subscriptions.append(subscription)

    def text(self, document_id: UUID) -> str:
        return self._handles[document_id].ydoc.text

    async def type(self, document_id: UUID, text: str, *, relay: bool = True) -> None:
        """A browser types ``text`` at the end: applied, stored, and relayed unless ``relay`` is False."""
        client = YDocument()
        client.apply_update(self._handles[document_id].ydoc.get_state())
        end = len(client.text)
        update = client.apply_edits([(end, end, text)])
        await self.components.manager.handle_update(document_id, update, origin="client")
        if relay:
            await self.components.redis_bridge.publish(document_id, "client", encode_update(update))

    async def close(self) -> None:
        """Stop the replica: its subscriptions, its background tasks and its in-memory copies are gone."""
        subscriptions, self._subscriptions = self._subscriptions, []
        for subscription in subscriptions:
            await subscription.aclose()
        await self.components.manager.aclose()
        await self._redis.aclose()


@pytest.fixture
def redis_server() -> FakeServer:
    return FakeServer()


async def _make_project_doc(db_session: AsyncSession) -> tuple[UUID, UUID]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.flush()
    return project.id, entity.id


async def _converged(a: _Replica, b: _Replica, document_id: UUID, *expected: str) -> None:
    """Wait until both replicas hold the same text and it contains ``expected`` (fails at a deadline)."""
    deadline = monotonic() + 3
    while True:
        a_text, b_text = a.text(document_id), b.text(document_id)
        if a_text == b_text and all(piece in a_text for piece in expected):
            return
        if monotonic() > deadline:
            raise AssertionError(f"replicas did not converge: A={a_text!r} B={b_text!r}")
        await asyncio.sleep(0.01)


async def _stored_text(db_session: AsyncSession, document_id: UUID) -> str:
    state, _seq = await CrdtStore(session_factory(db_session)).load(document_id)
    assert state is not None
    stored = YDocument()
    stored.apply_update(state)
    return stored.text


async def test_edits_on_both_replicas_converge(db_session: AsyncSession, redis_server: Any) -> None:
    _project_id, doc_id = await _make_project_doc(db_session)
    a, b = _Replica("replica-a", db_session, redis_server), _Replica("replica-b", db_session, redis_server)
    try:
        await a.open(doc_id)
        await b.open(doc_id)
        await a.type(doc_id, "hello ")
        await b.type(doc_id, "world")
        await _converged(a, b, doc_id, "hello ", "world")
        # The relayed update is applied to B's copy but is not stored a second time.
        stored_rows = await db_session.scalar(
            select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == doc_id)
        )
        assert stored_rows == 2
    finally:
        await a.close()
        await b.close()


async def test_compaction_on_either_replica_drops_no_stored_update(
    db_session: AsyncSession, redis_server: Any
) -> None:
    _project_id, doc_id = await _make_project_doc(db_session)
    a, b = _Replica("replica-a", db_session, redis_server), _Replica("replica-b", db_session, redis_server)
    try:
        await a.open(doc_id)
        await b.open(doc_id)
        await a.type(doc_id, "alpha", relay=False)  # stored by A, not yet relayed: B's copy lacks it
        await b.type(doc_id, "beta")
        await b.components.manager.flush(doc_id)  # B compacts while its copy is partial
        await a.components.manager.flush(doc_id)  # then A compacts
        stored = await _stored_text(db_session, doc_id)
        assert "alpha" in stored
        assert "beta" in stored
    finally:
        await a.close()
        await b.close()


async def test_forced_flush_on_a_writes_the_edit_typed_on_b(
    db_session: AsyncSession, redis_server: Any
) -> None:
    project_id, doc_id = await _make_project_doc(db_session)
    a, b = _Replica("replica-a", db_session, redis_server), _Replica("replica-b", db_session, redis_server)
    try:
        await a.open(doc_id)
        await b.open(doc_id)
        await b.type(doc_id, "typed on B", relay=False)  # acknowledged by B, unknown to A's memory
        await flush_open_project_docs(a.components, db_session, project_id)
        content = await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id))
        assert content == "typed on B"
    finally:
        await a.close()
        await b.close()


async def test_a_replica_stopping_loses_no_acknowledged_edit(
    db_session: AsyncSession, redis_server: Any
) -> None:
    project_id, doc_id = await _make_project_doc(db_session)
    a, b = _Replica("replica-a", db_session, redis_server), _Replica("replica-b", db_session, redis_server)
    fresh = _Replica("replica-c", db_session, redis_server)
    try:
        await a.open(doc_id)
        await b.open(doc_id)
        await a.type(doc_id, "kept ")
        await _converged(a, b, doc_id, "kept ")
        await a.close()  # replica A dies without a release: only the stored state remains
        await b.type(doc_id, "after")
        await flush_open_project_docs(b.components, db_session, project_id)
        await fresh.open(doc_id)
        assert "kept " in fresh.text(doc_id)
        assert "after" in fresh.text(doc_id)
        content = await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id))
        assert content is not None and "kept" in content and "after" in content
    finally:
        await fresh.close()
        await b.close()
        await a.close()
