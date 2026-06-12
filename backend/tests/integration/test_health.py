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


async def test_ready_ok_with_fake_redis_and_test_db(async_client: AsyncClient) -> None:
    resp = await async_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"redis": "ok", "db": "ok"}}


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


async def test_ready_503_when_db_broken(app: Any, async_client: AsyncClient) -> None:
    app.state.db_engine = FakeEngineBroken()
    resp = await async_client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["db"] == "error"
