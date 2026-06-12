"""Spec 66: two in-process pycrdt clients converge through the real server relay.

Manager-level exchanges (deterministic) plus one endpoint-level relay check. No
browser, no real network, fake Redis only. Observes behaviour — no prod change.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.collab.protocol import SyncStep2, SyncUpdate, read_message
from inkstave.collab.ydocument import YDocument
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import read_content_for_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import (
    ASGIWebSocketClient,
    apply_update_message,
    install_collab,
    make_update,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


def _apply_sync(doc: YDocument, data: bytes) -> None:
    """Apply an encoded SyncStep2/SyncUpdate frame into ``doc``."""
    parsed = read_message(data)
    if isinstance(parsed, (SyncStep2, SyncUpdate)):
        doc.apply_update(parsed.update)


async def _empty_doc(db_session: AsyncSession):
    owner = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, owner.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await db_session.flush()
    return owner, project, entity


async def test_concurrent_edits_converge(app: Any, db_session: AsyncSession, redis: Any) -> None:
    components = install_collab(app, db_session, redis)
    _owner, _project, entity = await _empty_doc(db_session)
    doc_id = entity.id
    mgr = components.manager
    await mgr.acquire(doc_id)
    try:
        # Two independent clients, both synced from the same empty server doc.
        a = YDocument()
        b = YDocument()
        # Concurrent edits — neither sees the other's before producing its update.
        update_a = a.replace_text("Hello ")
        update_b = b.replace_text("World")
        # The server applies + relays both; each client applies the other's update.
        relay_a = await mgr.handle_update(doc_id, update_a, origin="A")
        relay_b = await mgr.handle_update(doc_id, update_b, origin="B")
        b.apply_update(relay_a)
        a.apply_update(relay_b)

        server_text = await mgr.current_text(doc_id)
        assert a.text == b.text == server_text  # AC1 — convergence
        # AC1 — equal logical state. Raw state-vector *bytes* are not comparable: the
        # (client, clock) map has no canonical encoding order, so two converged docs
        # can serialise their vectors differently. Assert instead that neither client
        # is missing anything from the other — both cross-diffs are the empty update.
        _EMPTY_UPDATE = b"\x00\x00"
        assert a.diff(b.get_state_vector()) == _EMPTY_UPDATE
        assert b.diff(a.get_state_vector()) == _EMPTY_UPDATE
        assert a.text.count("Hello ") == 1  # AC2 — no loss / no dup
        assert a.text.count("World") == 1

        # AC3 — re-applying an already-seen update is a no-op.
        before = a.text
        a.apply_update(relay_b)
        assert a.text == before
    finally:
        await mgr.release(doc_id)


async def test_offline_client_merges_on_reconnect(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis)
    _owner, _project, entity = await _empty_doc(db_session)
    doc_id = entity.id
    mgr = components.manager
    await mgr.acquire(doc_id)
    try:
        a = YDocument()  # stays "connected"
        b = YDocument()  # goes "offline"

        # While B is offline, A edits and the server applies it.
        update_a = a.replace_text("Aedit ")
        await mgr.handle_update(doc_id, update_a, origin="A")

        # B makes 3 edits offline; updates are buffered, not sent.
        buffered = [
            b.replace_text("B1 "),
            b.replace_text("B1 B2 "),
            b.replace_text("B1 B2 B3 "),
        ]

        # Reconnect: exchange a sync step (B receives A's interim edit), then
        # replay the buffered updates through the server and relay them to A.
        step2, _server_step1 = await mgr.handle_sync_step1(doc_id, b.get_state_vector())
        _apply_sync(b, step2)  # AC5 — B now has A's edit too
        for update in buffered:
            relay = await mgr.handle_update(doc_id, update, origin="B")
            a.apply_update(relay)

        server_text = await mgr.current_text(doc_id)
        assert a.text == b.text == server_text  # AC4 — two-way convergence
        for token in ("B1", "B2", "B3"):
            assert token in server_text  # AC4 — all offline edits present
        assert "Aedit" in b.text  # AC5 — A's interim edit merged into B
    finally:
        await mgr.release(doc_id)


async def test_converged_text_visible_to_bridge(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    # Tiny debounce so the bridge flush resolves fast; we also force-flush below.
    components = install_collab(app, db_session, redis, collab_text_flush_debounce_ms=10)
    _owner, _project, entity = await _empty_doc(db_session)
    doc_id = entity.id
    mgr = components.manager
    await mgr.acquire(doc_id)
    try:
        a = YDocument()
        b = YDocument()
        relay_a = await mgr.handle_update(doc_id, a.replace_text("alpha "), origin="A")
        relay_b = await mgr.handle_update(doc_id, b.replace_text("beta"), origin="B")
        b.apply_update(relay_a)
        a.apply_update(relay_b)
        server_text = await mgr.current_text(doc_id)

        await mgr.flush(doc_id)  # force the CRDT → documents.content bridge
    finally:
        await mgr.release(doc_id)

    # AC6 — what a compile job / REST reader consumes equals the converged text.
    content = await read_content_for_collab(db_session, doc_id)
    assert content == server_text
    assert "alpha " in content and "beta" in content


async def test_relay_excludes_origin(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    owner, project, entity = await _empty_doc(db_session)
    from inkstave.auth.tokens import build_token_service
    from inkstave.config import get_settings

    token, _ = build_token_service(get_settings()).create_access_token(owner)
    path = f"/ws/collab/projects/{project.id}/documents/{entity.id}"

    async with (
        ASGIWebSocketClient(app, path, query=f"token={token}") as sender,
        ASGIWebSocketClient(app, path, query=f"token={token}") as peer,
    ):
        await sender.expect_accept()
        await sender.receive_bytes()  # server step1
        await peer.expect_accept()
        await peer.receive_bytes()

        await sender.send_bytes(make_update("relayed edit"))
        relayed = YDocument()
        apply_update_message(relayed, await peer.receive_bytes())  # AC7 — peer receives
        assert relayed.text == "relayed edit"
        await sender.expect_no_message(0.1)  # AC7 — origin gets no self-echo
