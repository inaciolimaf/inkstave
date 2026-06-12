"""Integration tests for the compile HTTP API + SSE (spec 22)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.compile.stream import publish_status
from inkstave.config import get_settings
from inkstave.dependencies import get_compile_enqueuer
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def enqueue(self, compile_id: UUID) -> str | None:
        self.calls.append(compile_id)
        return f"job-{compile_id}"


@pytest.fixture
def enqueuer(app: Any) -> FakeEnqueuer:
    fake = FakeEnqueuer()
    app.dependency_overrides[get_compile_enqueuer] = lambda: fake
    return fake


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project(client: AsyncClient, headers: dict[str, str]) -> str:
    return str(
        (await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"]
    )


def _url(pid: str) -> str:
    return f"/api/v1/projects/{pid}/compile"


async def test_enqueue_returns_202_and_creates_queued_row(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.post(_url(pid), json={}, headers=headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["main_file"] == "main.tex"
    assert len(enqueuer.calls) == 1
    assert str(enqueuer.calls[0]) == body["id"]


async def test_get_compile_status(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    cid = (await async_client.post(_url(pid), json={}, headers=headers)).json()["id"]
    resp = await async_client.get(f"{_url(pid)}/{cid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


async def test_latest_404_then_returns(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    assert (await async_client.get(f"{_url(pid)}/latest", headers=headers)).status_code == 404
    cid = (await async_client.post(_url(pid), json={}, headers=headers)).json()["id"]
    latest = await async_client.get(f"{_url(pid)}/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == cid


async def test_coalesce_returns_inflight(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    first = (await async_client.post(_url(pid), json={}, headers=headers)).json()["id"]
    second = await async_client.post(_url(pid), json={}, headers=headers)
    assert second.status_code == 202
    assert second.json()["id"] == first
    assert len(enqueuer.calls) == 1  # no new enqueue


async def test_concurrency_cap_429(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    await async_client.post(_url(pid), json={}, headers=headers)  # 1 active (cap = 1)
    forced = await async_client.post(_url(pid), json={"force": True}, headers=headers)
    assert forced.status_code == 429
    assert forced.json()["error"]["type"] == "compile_concurrency_limit"
    assert "Retry-After" in forced.headers
    assert len(enqueuer.calls) == 1  # no new job enqueued


async def test_cancel_queued_compile(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    cid = (await async_client.post(_url(pid), json={}, headers=headers)).json()["id"]
    resp = await async_client.post(f"{_url(pid)}/{cid}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # Idempotent: cancelling again returns the terminal status.
    again = await async_client.post(f"{_url(pid)}/{cid}/cancel", headers=headers)
    assert again.json()["status"] == "cancelled"


async def test_cross_user_is_404(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(async_client, headers_a)
    cid = (await async_client.post(_url(pid), json={}, headers=headers_a)).json()["id"]
    resp = await async_client.get(f"{_url(pid)}/{cid}", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "project_not_found"


async def test_requires_auth(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    assert (await async_client.post(_url(pid), json={})).status_code == 401


async def test_sse_stream_emits_snapshot_then_transitions(redis: Any) -> None:
    """Exercise the SSE generator directly (avoids in-process httpx stream deadlock)."""
    from inkstave.compile.stream import sse_stream

    cid = uuid4()

    async def snapshot() -> dict[str, Any]:
        return {"id": str(cid), "status": "queued"}

    gen = sse_stream(redis, cid, snapshot, keepalive_seconds=5)
    first = await anext(gen)
    assert b'"status": "queued"' in first

    await publish_status(redis, cid, {"id": str(cid), "status": "running"})
    second = await anext(gen)
    assert b'"status": "running"' in second

    await publish_status(redis, cid, {"id": str(cid), "status": "success"})
    third = await anext(gen)
    assert b'"status": "success"' in third

    # Terminal state closes the stream.
    with pytest.raises(StopAsyncIteration):
        await anext(gen)


async def test_sse_endpoint_snapshot_for_terminal_compile(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    cid = (await async_client.post(_url(pid), json={}, headers=headers)).json()["id"]
    # Cancel -> terminal, so the SSE stream sends one snapshot and closes (no hang).
    await async_client.post(f"{_url(pid)}/{cid}/cancel", headers=headers)
    resp = await async_client.get(f"{_url(pid)}/{cid}/events", headers=headers)
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert '"status": "cancelled"' in resp.text


async def test_sse_unknown_compile_404(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEnqueuer
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.get(f"{_url(pid)}/{uuid4()}/events", headers=headers)
    assert resp.status_code == 404
