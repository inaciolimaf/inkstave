"""Integration tests for the agent HTTP API: sessions, messages, listing (spec 44)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.settings import AgentSettings

from ._agent_api_support import API, _auth, _FakeEnqueuer, enqueuer, seed

__all__ = ["enqueuer", "seed"]

pytestmark = pytest.mark.integration


# --- HTTP: sessions + authz ------------------------------------------------ #


async def test_session_create_authz(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await async_client.post(
        f"{API}/{seed.project.id}/agent/sessions", json={"title": "Help"}, headers=seed.headers
    )
    assert r.status_code == 201 and r.json()["run_state"] == "idle"  # AC1

    _outsider, outsider_h = await _auth(db_session)
    forbidden = await async_client.post(
        f"{API}/{seed.project.id}/agent/sessions", json={}, headers=outsider_h
    )
    assert forbidden.status_code == 403  # non-member
    missing = await async_client.post(
        f"{API}/{uuid4()}/agent/sessions", json={}, headers=seed.headers
    )
    assert missing.status_code == 404  # unknown project


async def test_post_message_enqueues_and_conflicts(
    seed: SimpleNamespace, async_client: AsyncClient, enqueuer: _FakeEnqueuer
) -> None:
    base = f"{API}/{seed.project.id}/agent"
    sid = (await async_client.post(f"{base}/sessions", json={}, headers=seed.headers)).json()["id"]

    posted = await async_client.post(
        f"{base}/sessions/{sid}/messages", json={"content": "hi"}, headers=seed.headers
    )
    assert posted.status_code == 202  # AC2
    body = posted.json()
    assert body["run_id"] and body["stream_url"].endswith(f"/runs/{body['run_id']}/events")
    assert len(enqueuer.calls) == 1

    detail = (await async_client.get(f"{base}/sessions/{sid}", headers=seed.headers)).json()
    assert detail["session"]["run_state"] == "queued"

    # A second post while a run is active → 409.
    again = await async_client.post(
        f"{base}/sessions/{sid}/messages", json={"content": "again"}, headers=seed.headers
    )
    assert again.status_code == 409


async def test_too_long_message_is_400(
    seed: SimpleNamespace, async_client: AsyncClient, enqueuer: _FakeEnqueuer
) -> None:
    # Spec 45: a length-cap violation is a bad request (400), not a conflict (409).
    base = f"{API}/{seed.project.id}/agent"
    sid = (await async_client.post(f"{base}/sessions", json={}, headers=seed.headers)).json()["id"]
    oversized = "x" * (AgentSettings().agent_max_message_chars + 1)
    r = await async_client.post(
        f"{base}/sessions/{sid}/messages", json={"content": oversized}, headers=seed.headers
    )
    assert r.status_code == 400


# --- HTTP: list sessions (paginated) --------------------------------------- #


async def test_list_sessions_http(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    base = f"{API}/{seed.project.id}/agent"

    async def _create(title: str) -> dict[str, Any]:
        r = await async_client.post(f"{base}/sessions", json={"title": title}, headers=seed.headers)
        return r.json()

    s1 = await _create("A")
    s2 = await _create("B")

    listed = await async_client.get(f"{base}/sessions", headers=seed.headers)
    assert listed.status_code == 200
    body = listed.json()
    assert isinstance(body, list)
    ids = {row["id"] for row in body}
    assert s1["id"] in ids and s2["id"] in ids  # AC3: created sessions appear
    # Pagination shape: limit param is honoured and bounded.
    capped = await async_client.get(f"{base}/sessions", params={"limit": 1}, headers=seed.headers)
    assert capped.status_code == 200 and len(capped.json()) == 1

    # Authorization: a non-member is denied the list.
    _outsider, outsider_h = await _auth(db_session)
    denied = await async_client.get(f"{base}/sessions", headers=outsider_h)
    assert denied.status_code == 403
