"""End-to-end: edits over the spec-29 WS are captured into history (spec 36 wiring)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.history import HistoryUpdate
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import set_content_from_collab
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.collab_ws_harness import ASGIWebSocketClient, install_collab, make_update
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _setup(db_session: AsyncSession):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "")
    await db_session.flush()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return project, entity, token


async def _history_rows(db_session: AsyncSession, doc_id: Any) -> int:
    stmt = select(func.count()).select_from(HistoryUpdate).where(HistoryUpdate.doc_id == doc_id)
    return int(await db_session.scalar(stmt))


async def test_ws_edit_is_captured_on_room_close(
    app: Any, db_session: AsyncSession, redis: Any
) -> None:
    # High debounce so capture buffers (never fires the idle timer mid-test).
    install_collab(app, db_session, redis, history_debounce_ms=10_000_000)
    project, entity, token = await _setup(db_session)
    path = f"/ws/collab/projects/{project.id}/documents/{entity.id}"

    async with ASGIWebSocketClient(app, path, query=f"token={token}") as ws:
        await ws.expect_accept()
        await ws.receive_bytes()  # server step 1
        await ws.send_bytes(make_update("history via ws"))
        await asyncio.sleep(0.05)
        # AC8 end-to-end: capture buffered, nothing written yet.
        assert await _history_rows(db_session, entity.id) == 0

    # Disconnect → room empty → flush (AC9 end-to-end): the edit is persisted.
    await asyncio.sleep(0.05)
    assert await _history_rows(db_session, entity.id) == 1
