"""Keepalive of the collab WebSocket: a silent peer is closed, a responsive one stays (spec 29).

The server sends an application-level ping (message tag 2) every
``COLLAB_WS_PING_INTERVAL_SECONDS``; the browser answers with a pong (tag 3). Any inbound
frame counts as proof of life. A peer silent for interval + pong timeout is closed with
4000. The intervals are small here so the tests stay fast.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.collab_ws_harness import ASGIWebSocketClient, install_collab
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PING = b"\x02"  # heartbeat ping: an outer tag no y-protocols message uses
PONG = b"\x03"  # heartbeat pong, the browser's answer
FAST = {"collab_ws_ping_interval_seconds": 0.05, "collab_ws_pong_timeout_seconds": 0.3}


async def _setup(db_session: AsyncSession) -> tuple[Any, Any, str]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await db_session.flush()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return project, entity, token


def _path(project_id: Any, document_id: Any) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


async def _next_ping(ws: ASGIWebSocketClient) -> None:
    """Skip handshake frames until the server's ping arrives; fail on a close."""
    while True:
        message = await ws.receive()
        assert message["type"] == "websocket.send", message
        if message["bytes"][:1] == PING:
            return


async def test_silent_peer_is_closed_4000_after_ping_and_pong_timeout(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis, **FAST)
    project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        await _next_ping(ws)  # the server pings; this client never answers
        while True:  # more pings may still arrive before the close
            message = await ws.receive(timeout=2.0)
            if message["type"] == "websocket.close":
                break
        assert message["code"] == 4000


async def test_peer_that_answers_pings_stays_connected(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis, **FAST)
    project, entity, token = await _setup(db_session)
    async with ASGIWebSocketClient(app, _path(project.id, entity.id), query=f"token={token}") as ws:
        await ws.expect_accept()
        for _ in range(6):  # several full intervals, each answered
            await _next_ping(ws)
            await ws.send_bytes(PONG)
