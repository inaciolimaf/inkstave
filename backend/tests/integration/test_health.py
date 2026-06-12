"""Integration tests for the liveness/readiness probes (fake Redis + test DB)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import FakeEngineBroken, FakeRedisHanging, FakeRedisRaising

pytestmark = pytest.mark.integration


async def test_health_ok(async_client: AsyncClient) -> None:
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_ok_redis_only(async_client: AsyncClient) -> None:
    # Spec 02 §5.2 / AC3 / AC4: /ready is Redis-only; no DB check, no DB key.
    resp = await async_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"redis": "ok"}}


async def test_ready_503_when_redis_raises(app: Any, async_client: AsyncClient) -> None:
    app.state.redis = FakeRedisRaising()
    resp = await async_client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"] == "error"


async def test_ready_503_when_redis_hangs(app: Any, async_client: AsyncClient) -> None:
    app.state.redis = FakeRedisHanging()
    resp = await async_client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["redis"] == "error"


async def test_ready_ignores_broken_db(app: Any, async_client: AsyncClient) -> None:
    # AC3: a broken DB must not affect /ready as long as Redis is up.
    app.state.db_engine = FakeEngineBroken()
    resp = await async_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"redis": "ok"}}


async def test_readyz_ok_with_db_and_redis(async_client: AsyncClient) -> None:
    # Spec 51: /readyz keeps the DB+Redis check.
    resp = await async_client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"db": "ok", "redis": "ok"}}


async def test_readyz_503_when_db_broken(app: Any, async_client: AsyncClient) -> None:
    app.state.db_engine = FakeEngineBroken()
    resp = await async_client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json()["checks"]["db"] == "error"
