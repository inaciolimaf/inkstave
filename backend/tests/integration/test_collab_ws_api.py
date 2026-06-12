"""Integration tests for the collaboration WebSocket endpoint (spec 29)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.collab.protocol import AwarenessMessage, SyncStep1, read_message
from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.crdt import CrdtUpdate
from inkstave.db.models.document import Document
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import (
    ASGIWebSocketClient,
    apply_update_message,
    awareness_message,
    install_collab,
    make_update,
)
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _setup(db_session: AsyncSession, content: str = ""):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    if content:
        await set_content_from_collab(db_session, entity.id, content)
    await db_session.flush()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, project, entity, token


def _path(project_id: Any, document_id: Any) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


# --- auth / authz (criteria 1-2) ------------------------------------------- #


async def test_missing_token_closes_4401(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, _token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id)) as ws:
        assert await ws.close_code() == 4401


async def test_invalid_token_closes_4401(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, _token = await _setup(db_session)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query="token=not-a-jwt"
    ) as ws:
        assert await ws.close_code() == 4401


async def test_non_member_closes_4403(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, _token = await _setup(db_session)
    other = await UserFactory.create(db_session)
    await db_session.flush()
    other_token, _ = build_token_service(get_settings()).create_access_token(other)
    async with ASGIWebSocketClient(
        app, _path(project.id, entity.id), query=f"token={other_token}"
    ) as ws:
        assert await ws.close_code() == 4403


async def test_unknown_project_closes_4404(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, _project, _entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(uuid4(), uuid4()), query=f"token={token}") as ws:
        assert await ws.close_code() == 4404


async def test_unknown_document_closes_4404(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, _entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, uuid4()), query=f"token={token}") as ws:
        assert await ws.close_code() == 4404


# --- handshake (criterion 3) ----------------------------------------------- #


async def test_handshake_sends_server_step1(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session, content="seed")
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        first = await ws.receive_bytes()
        assert isinstance(read_message(first), SyncStep1)


async def test_handshake_sends_awareness_snapshot(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    """AC3: a joining client receives Sync Step 1 **and** the pre-existing awareness
    snapshot before sending anything (router's ``if snapshot is not None`` branch)."""
    from pycrdt import Awareness, Doc

    components = install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session, content="seed")

    # Pre-populate awareness for the room so a snapshot exists at connect time.
    seeder = Awareness(Doc())
    seeder.set_local_state({"user": "bob"})
    raw_update = seeder.encode_awareness_update([seeder.client_id])
    components.awareness.apply(entity.id, raw_update)

    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        first = await ws.receive_bytes()
        assert isinstance(read_message(first), SyncStep1)
        # The snapshot is delivered as the second frame, before the client sends.
        second = await ws.receive_bytes()
        assert isinstance(read_message(second), AwarenessMessage)


# --- two-client convergence + no echo (criterion 4) ------------------------ #


async def test_two_clients_converge(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    path = _path(project.id, entity.id)
    async with (
        ASGIWebSocketClient(app, path, query=f"token={token}") as a,
        ASGIWebSocketClient(app, path, query=f"token={token}") as b,
    ):
        await a.expect_accept()
        await a.receive_bytes()  # server step1
        await b.expect_accept()
        await b.receive_bytes()

        await a.send_bytes(make_update("hi"))
        relayed = await b.receive_bytes()  # B gets A's update
        await a.expect_no_message()  # A is not echoed

        local = YDocument()
        apply_update_message(local, relayed)
        assert local.text == "hi"


# --- awareness relay + offline (criterion 6) ------------------------------- #


async def test_awareness_relay_and_offline(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    path = _path(project.id, entity.id)
    b = ASGIWebSocketClient(app, path, query=f"token={token}")
    async with b:
        await b.expect_accept()
        await b.receive_bytes()  # server step1
        async with ASGIWebSocketClient(app, path, query=f"token={token}") as a:
            await a.expect_accept()
            await a.receive_bytes()
            # B may receive A's awareness snapshot on join; drain non-awareness noise.
            _client_id, awareness = awareness_message({"user": "alice"})
            await a.send_bytes(awareness)
            relayed = await b.receive_bytes()
            assert isinstance(read_message(relayed), AwarenessMessage)
        # A disconnected -> B receives an awareness "offline" update for A.
        offline = await b.receive_bytes()
        assert isinstance(read_message(offline), AwarenessMessage)


# --- persistence integration (criterion 7) --------------------------------- #


async def test_update_persists_and_bridges_text(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        await ws.send_bytes(make_update("Hello WS"))
        await asyncio.sleep(0.05)  # let dispatch apply + append

        count = await db_session.scalar(
            select(func.count()).select_from(CrdtUpdate).where(CrdtUpdate.document_id == entity.id)
        )
        assert count >= 1

        await components.manager.flush(entity.id)
        content = await db_session.scalar(
            select(Document.content).where(Document.entity_id == entity.id)
        )
        assert content == "Hello WS"


# --- disconnect cleanup (criterion 8) -------------------------------------- #


async def test_ws_connection_gauge_rises_and_returns(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    from prometheus_client import REGISTRY

    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)

    def gauge() -> float:
        return (
            REGISTRY.get_sample_value("inkstave_ws_connections_active", {"kind": "collab"}) or 0.0
        )

    before = gauge()
    ws = ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}")
    async with ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        assert gauge() == before + 1  # AC6: rises by 1 on connect
    await asyncio.sleep(0.05)
    assert gauge() == before  # returns to baseline on disconnect (finally-balanced)


async def test_disconnect_tears_down_room(app: Any, db_session: AsyncSession, redis: Any) -> None:
    components = install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    ws = ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}")
    async with ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        assert components.rooms.room_count() == 1
        assert entity.id in components.subscriptions

    await asyncio.sleep(0.05)
    assert components.rooms.room_count() == 0
    assert entity.id not in components.subscriptions
    entry = components.manager._entries.get(entity.id)
    assert entry is None or entry.refcount == 0


# --- bad / oversize / rate-limited frames (criteria 10-11) ----------------- #


async def test_text_frame_closes_4400(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        await ws.send_text("hello")
        assert await ws.close_code() == 4400


async def test_oversize_frame_closes_4400(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis, collab_ws_max_frame_bytes=64)
    _user, project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        await ws.send_bytes(b"x" * 100)
        assert await ws.close_code() == 4400


async def test_rate_limit_closes_4429(app: Any, db_session: AsyncSession, redis: Any) -> None:
    install_collab(app, db_session, redis, collab_ws_max_msgs_per_sec=3)
    _user, project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        await ws.receive_bytes()
        for _ in range(5):  # unknown-tag frames are ignored but still rate-counted
            await ws.send_bytes(b"\x09unknown")
        assert await ws.close_code() == 4429
