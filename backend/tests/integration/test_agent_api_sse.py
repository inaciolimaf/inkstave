"""Integration tests for the SSE events route and HTTP cancel route (spec 44)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.agent.api.events import RedisEventSink, run_channel
from inkstave.agent.models import AgentRunState

from ._agent_api_support import API, _auth, _make_session, seed

__all__ = ["seed"]

pytestmark = pytest.mark.integration


# --- HTTP: SSE events route (query-param token auth) ----------------------- #


async def test_sse_events_route_streams_and_closes(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    # AC1/issue 176: GET the SSE events route via httpx streaming, authenticating
    # through the query-param token (the SSE auth path), and assert the event
    # sequence + terminal close — exercising the route, _sse_user, and membership.
    import asyncio

    session = await _make_session(db_session, seed)
    await db_session.commit()
    run_id = str(session.active_run_id)
    token = seed.headers["Authorization"].removeprefix("Bearer ")
    path = (
        f"{API}/{seed.project.id}/agent/sessions/{session.id}/runs/{run_id}/events"
        f"?access_token={token}"
    )

    collected: list[bytes] = []

    async def consume() -> None:
        async with async_client.stream("GET", path) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for chunk in resp.aiter_bytes():
                collected.append(chunk)

    task = asyncio.create_task(consume())
    # Wait until the SSE endpoint has actually SUBSCRIBED before emitting. A fixed
    # sleep races under load and drops the live-only `token` event (only the
    # terminal `done` is replayable for late subscribers), which made this flaky.
    channel = run_channel(run_id)
    for _ in range(300):
        subs = await redis.pubsub_numsub(channel)
        if sum(count for _, count in subs) >= 1:
            break
        await asyncio.sleep(0.01)
    else:  # pragma: no cover - the subscriber always attaches well within 3s
        raise AssertionError("SSE subscriber did not attach")
    redis_sink = RedisEventSink(redis, run_id, ttl_seconds=60)
    await redis_sink.emit("token", text="Hi")
    await redis_sink.emit("done", final_text="Hi")
    await asyncio.wait_for(task, timeout=3)

    text = b"".join(collected)
    assert b"event: token" in text and b"Hi" in text
    assert b"event: done" in text  # terminal closes the stream


async def test_sse_events_route_requires_auth(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    session = await _make_session(db_session, seed)
    await db_session.commit()
    run_id = str(session.active_run_id)
    base = f"{API}/{seed.project.id}/agent/sessions/{session.id}/runs/{run_id}/events"

    unauth = await async_client.get(base)
    assert unauth.status_code == 401  # no token at all

    _outsider, outsider_h = await _auth(db_session)
    token = outsider_h["Authorization"].removeprefix("Bearer ")
    denied = await async_client.get(f"{base}?access_token={token}")
    assert denied.status_code == 403  # authenticated non-member


# --- HTTP: cancel run ------------------------------------------------------ #


async def test_cancel_run_http(
    seed: SimpleNamespace, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # AC2/issue 177: POST the cancel route; member gets 2xx and the run goes to
    # a cancelling/cancelled state; a non-member is rejected.
    session = await _make_session(db_session, seed)
    await db_session.commit()
    run_id = str(session.active_run_id)
    base = f"{API}/{seed.project.id}/agent/sessions/{session.id}/runs/{run_id}/cancel"

    resp = await async_client.post(base, headers=seed.headers)
    assert resp.status_code == 202  # accepted

    detail = await async_client.get(
        f"{API}/{seed.project.id}/agent/sessions/{session.id}", headers=seed.headers
    )
    assert detail.json()["session"]["run_state"] == AgentRunState.cancelling.value

    # A non-member cannot cancel another project's run.
    _outsider, outsider_h = await _auth(db_session)
    denied = await async_client.post(base, headers=outsider_h)
    assert denied.status_code == 403
