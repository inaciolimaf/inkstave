"""Integration tests for observability HTTP surface (spec 51)."""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.observability.log import JsonLogFormatter
from inkstave.observability.tracing import current_trace_id
from tests.conftest import FakeRedisRaising
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _AccessLog:
    """Capture the access logger's formatted JSON output (clearing the level cache)."""

    def __init__(self) -> None:
        self._buf = io.StringIO()
        self._handler = logging.StreamHandler(self._buf)
        self._handler.setFormatter(
            JsonLogFormatter(service="inkstave-backend", env="test", log_stacks=True)
        )
        self._logger = logging.getLogger("inkstave.access")

    def __enter__(self) -> _AccessLog:
        self._prev = self._logger.level
        self._prev_disabled = self._logger.disabled
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.DEBUG)
        # The test harness disables existing loggers (dictConfig); re-enable for capture.
        self._logger.disabled = False
        logging.Logger.manager._clear_cache()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev)
        self._logger.disabled = self._prev_disabled

    def finish_logs(self) -> list[dict[str, Any]]:
        return [
            obj
            for line in self._buf.getvalue().splitlines()
            if line.strip()
            for obj in [json.loads(line)]
            if obj.get("message") == "request"
        ]


async def test_request_id_roundtrip_and_finish_log(async_client: AsyncClient) -> None:
    with _AccessLog() as cap:
        resp = await async_client.get("/api/v1/openapi.json", headers={"X-Request-ID": "smoke-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "smoke-123"  # AC2

    finish = cap.finish_logs()
    assert finish, "expected exactly one finish log"
    f = finish[-1]
    assert f["request_id"] == "smoke-123"  # AC1: request_id in the JSON line
    assert f["http.method"] == "GET"
    assert f["http.path"] == "/api/v1/openapi.json"  # route template, never the raw id
    assert f["http.status_code"] == 200
    assert "http.duration_ms" in f
    assert f["trace_id"] == "smoke-123"  # OTEL off → trace_id == request_id (AC10)
    assert current_trace_id() is None  # no OpenTelemetry initialized (AC10)


async def test_malformed_inbound_request_id_is_replaced(async_client: AsyncClient) -> None:
    resp = await async_client.get(
        "/api/v1/openapi.json", headers={"X-Request-ID": "bad id with spaces!!"}
    )
    assert resp.headers["X-Request-ID"] != "bad id with spaces!!"  # AC2
    assert len(resp.headers["X-Request-ID"]) == 32  # a fresh uuid4 hex


async def test_metrics_endpoint(async_client: AsyncClient) -> None:
    await async_client.get("/api/v1/openapi.json")  # generate a finished request
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200  # AC5
    assert resp.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    body = resp.text
    for name in (
        "inkstave_http_requests_total",
        "inkstave_http_request_duration_seconds",
        "inkstave_build_info",
        "inkstave_agent_tokens_total",
        "inkstave_compile_duration_seconds",
        "inkstave_job_queue_depth",
    ):
        assert name in body
    assert 'inkstave_http_requests_total{method="GET",path="/api/v1/openapi.json"' in body


async def test_authenticated_finish_log_auto_propagates_user_id(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Spec 51 AC3: after auth resolves, the finish log auto-carries user_id + request_id
    without the handler threading them explicitly."""
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    headers = {"Authorization": f"Bearer {token}", "X-Request-ID": "auth-req-9"}

    with _AccessLog() as cap:
        resp = await async_client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 200

    finish = cap.finish_logs()
    assert finish, "expected a finish log for the authenticated request"
    f = finish[-1]
    # user_id was bound by the auth dependency, not passed by the handler (AC3).
    assert f["user_id"] == str(user.id)
    assert f["request_id"] == "auth-req-9"  # consistent correlation id


async def test_finish_log_http_path_is_route_template_not_raw_id(
    app: Any, async_client: AsyncClient
) -> None:
    """Spec 55 §5.1: http.path is the matched route template, never the raw id-bearing
    URL (a cardinality/PII risk). Register a parameterized route on the app under test."""
    from uuid import uuid4

    @app.get("/_test/items/{item_id}")
    async def _item(item_id: str) -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"item_id": item_id}

    raw_id = uuid4().hex
    with _AccessLog() as cap:
        resp = await async_client.get(f"/_test/items/{raw_id}")
    assert resp.status_code == 200

    finish = cap.finish_logs()
    assert finish, "expected a finish log for the parameterized request"
    f = finish[-1]
    assert f["http.path"] == "/_test/items/{item_id}"  # template, not the raw id
    assert raw_id not in f["http.path"]


async def test_healthz_always_ok_and_readyz_503_then_recovers(
    app: Any, async_client: AsyncClient, redis: Any
) -> None:
    assert (await async_client.get("/healthz")).json() == {"status": "ok"}  # AC9
    app.state.redis = FakeRedisRaising()
    readyz = await async_client.get("/readyz")
    assert readyz.status_code == 503 and readyz.json()["checks"]["redis"] == "error"
    # liveness is independent of dependencies
    assert (await async_client.get("/healthz")).status_code == 200

    # Spec 55 AC4: /readyz recovers to 200 once the dependency is healthy again.
    app.state.redis = redis
    recovered = await async_client.get("/readyz")
    assert recovered.status_code == 200
    assert recovered.json()["checks"]["redis"] == "ok"


async def test_metrics_survives_redis_down_at_scrape(app: Any, async_client: AsyncClient) -> None:
    app.state.redis = FakeRedisRaising()  # queue-depth sample must fail soft (AC12)
    resp = await async_client.get("/metrics")
    assert resp.status_code == 200
