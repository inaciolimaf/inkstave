"""Spec-30 refactor tests for the WebSocket layer: reconnect + leak bounds."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.collab.protocol import SyncStep2, encode_sync_step1, read_message
from inkstave.collab.ydocument import YDocument
from inkstave.config import get_settings
from inkstave.db.models.crdt import CrdtUpdate
from inkstave.db.models.project import Project
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.db.models.user import User
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import ASGIWebSocketClient, install_collab, make_update
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _poll(
    predicate: Callable[[], bool],
    attempts: int = 200,
    step: float = 0.005,
) -> None:
    """Wait deterministically for a positive (sync) condition (no fixed sleeps)."""
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(step)


async def _poll_async(
    predicate: Callable[[], Any],
    attempts: int = 200,
    step: float = 0.005,
) -> None:
    """Wait deterministically for a positive condition evaluated by a coroutine."""
    for _ in range(attempts):
        if await predicate():
            return
        await asyncio.sleep(step)


async def _setup(db_session: AsyncSession) -> tuple[User, Project, TreeEntity, str]:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await db_session.flush()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, project, entity, token


async def _update_count(db_session: AsyncSession, document_id: UUID) -> int:
    return int(
        await db_session.scalar(
            select(func.count())
            .select_from(CrdtUpdate)
            .where(CrdtUpdate.document_id == document_id)
        )
        or 0
    )


def _path(project_id: Any, document_id: Any) -> str:
    return f"/ws/collab/projects/{project_id}/documents/{document_id}"


async def test_reconnect_resyncs_and_converges(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    install_collab(app, db_session, redis)
    _user, project, entity, token = await _setup(db_session)
    path = _path(project.id, entity.id)

    # First session: send an update, then disconnect.
    async with ASGIWebSocketClient(app, path, query=f"token={token}") as a:
        await a.expect_accept()
        await a.receive_bytes()  # server step 1
        await a.send_bytes(make_update("persisted"))
        # Wait deterministically until the update is persisted (not a fixed sleep).
        await _poll_async(lambda: _update_count(db_session, entity.id))

    # Reconnect: run the sync handshake from a fresh state vector; the server's
    # step 2 must carry the prior update (no lost edit, no duplication).
    async with ASGIWebSocketClient(app, path, query=f"token={token}") as b:
        await b.expect_accept()
        first = read_message(await b.receive_bytes())  # server step 1
        local = YDocument()
        await b.send_bytes(encode_sync_step1(local.get_state_vector()))
        # The server already sent its step1 on connect (``first``), so it now replies
        # with just step2 (the diff). Drain a few messages until the step2 arrives
        # (tolerating an interleaved awareness snapshot) and apply it.
        for _ in range(3):
            parsed = read_message(await b.receive_bytes())
            if isinstance(parsed, SyncStep2):
                local.apply_update(parsed.update)
                break
        assert local.text == "persisted"
    assert first is not None


async def test_connect_disconnect_cycles_leave_no_leak(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    components = install_collab(app, db_session, redis, collab_idle_evict_seconds=0.02)
    _user, project, entity, token = await _setup(db_session)
    path = _path(project.id, entity.id)

    baseline_tasks = len(asyncio.all_tasks())
    for _ in range(3):
        async with ASGIWebSocketClient(app, path, query=f"token={token}") as ws:
            await ws.expect_accept()
            await ws.receive_bytes()
        # Wait deterministically for cleanup + idle eviction to drain this doc.
        await _poll(lambda: not components.manager._entries)

    # Rooms + subscriptions + per-doc maps all drained back to empty.
    assert components.rooms.room_count() == 0
    assert components.subscriptions == {}
    assert components.manager._entries == {}
    assert components.manager._locks == {}

    # Background tasks (writer/forwarder/evict) do not accumulate across cycles.
    await _poll(lambda: len(asyncio.all_tasks()) <= baseline_tasks + 1)
    assert len(asyncio.all_tasks()) <= baseline_tasks + 1
