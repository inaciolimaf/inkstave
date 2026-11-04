"""Integration tests for the project event stream (spec 117).

The stream is read through its generator, not the HTTP client: the ASGI transport buffers a
response until the body ends, and a live stream never ends on its own.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.discussion import MemberCheck, project_events_stream
from inkstave.modules.projects import role_for
from tests.integration._discussion_support import post_message, read_frames_until
from tests.integration._sharing_api_support import _add_member, _auth, _project

pytestmark = pytest.mark.integration

KEEPALIVE_S = 0.05  # injected so a membership re-check happens within a test's budget
DEADLINE_S = 2.0


def _events_url(project_id: str) -> str:
    return f"/api/v1/projects/{project_id}/events"


def _membership(db_session: AsyncSession, user_id: UUID, project_id: UUID) -> MemberCheck:
    async def is_member() -> bool:
        return await role_for(db_session, user_id, project_id) is not None

    return is_member


async def _consume(stream: AsyncIterator[bytes]) -> None:
    async for _ in stream:
        pass


async def test_events_stream_requires_membership(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    stranger, _ = await _auth(db_session, email="stranger@example.com")
    token, _ = build_token_service(get_settings()).create_access_token(stranger)

    response = await async_client.get(_events_url(pid), params={"access_token": token})
    assert response.status_code == 404
    assert response.json()["error"]["type"] == "project_not_found"


async def test_stream_endpoint_requires_a_token(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    assert (await async_client.get(_events_url(pid))).status_code == 401


async def test_member_receives_chat_events_live(
    async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    editor, _ = await _add_member(async_client, db_session, owner_h, pid, "ed@example.com", "editor")
    stream = project_events_stream(
        redis, UUID(pid), _membership(db_session, editor.id, UUID(pid)), KEEPALIVE_S
    )
    try:
        assert await asyncio.wait_for(anext(stream), DEADLINE_S) == b": connected\n\n"
        await post_message(async_client, owner_h, pid, "Oi")
        frames = await read_frames_until(stream, b"event: chat.message_created")
    finally:
        await stream.aclose()

    event_frame = frames[-1]
    assert event_frame.startswith(b"id: 1\nevent: chat.message_created\ndata: ")
    assert b'"body": "Oi"' in event_frame


async def test_events_stream_closes_after_removal(
    async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    editor, _ = await _add_member(async_client, db_session, owner_h, pid, "ed@example.com", "editor")
    stream = project_events_stream(
        redis, UUID(pid), _membership(db_session, editor.id, UUID(pid)), KEEPALIVE_S
    )
    assert await asyncio.wait_for(anext(stream), DEADLINE_S) == b": connected\n\n"

    removed = await async_client.delete(f"/api/v1/projects/{pid}/members/{editor.id}", headers=owner_h)
    assert removed.status_code == 204

    # Returns only when the generator ends; the deadline turns a stream that stays open into a failure.
    await asyncio.wait_for(_consume(stream), DEADLINE_S)
    assert owner.id != editor.id
