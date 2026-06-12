"""Integration tests for security hardening HTTP surface (spec 52)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Response
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.errors import RateLimitError
from inkstave.security.body_limit import BodySizeLimitMiddleware
from inkstave.security.rate_limit import RateLimitPolicy, rate_limit
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_SECURITY_HEADERS = (
    "x-frame-options",
    "x-content-type-options",
    "content-security-policy",
    "referrer-policy",
    "permissions-policy",
)


async def _auth(db_session: AsyncSession) -> tuple[dict[str, str], Any]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}, user


# --- secure headers (AC5) --------------------------------------------------- #


async def test_security_headers_present_on_404_and_200(async_client: AsyncClient) -> None:
    for path in ("/healthz", "/this-route-does-not-exist"):
        resp = await async_client.get(path)
        for header in _SECURITY_HEADERS:
            assert resp.headers.get(header), f"{header} missing on {path}"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert "x-powered-by" not in resp.headers  # framework banner stripped
        assert "strict-transport-security" not in resp.headers  # HSTS off in test


# --- body size limit (AC4: 413) --------------------------------------------- #


async def test_body_size_limit_returns_413() -> None:
    async def ok(_request: Any) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", ok, methods=["POST"])])

    class _Cap:
        max_request_body_bytes = 16
        max_upload_bytes = 16

    app.add_middleware(BodySizeLimitMiddleware, settings=_Cap())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        small = await client.post("/x", content=b"tiny")
        big = await client.post("/x", content=b"x" * 64)
    assert small.status_code == 200
    assert big.status_code == 413


# --- strict validation (AC4: 422 extra) ------------------------------------- #


async def test_extra_field_is_rejected_422(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, user = await _auth(db_session)
    project = await create_project(db_session, user.id, "P")
    await db_session.commit()
    resp = await async_client.post(
        f"/api/v1/projects/{project.id}/agent/sessions",
        json={"title": "ok", "evil_extra_field": "smuggled"},
        headers=headers,
    )
    assert resp.status_code == 422


# --- rate limiting (AC1/AC3) ------------------------------------------------ #


def _request(ip: str = "1.2.3.4") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/x",
            "headers": [],
            "client": (ip, 12345),
            "query_string": b"",
        }
    )


async def test_rate_limit_dependency_sets_headers_and_429s(redis: Any) -> None:
    policy = RateLimitPolicy(name="sec-test", limit=2, window_seconds=60, key="ip")
    dep = rate_limit(policy)
    settings = get_settings()
    response = Response()
    request = _request()
    for _ in range(2):
        await dep(request, response, user=None, redis=redis, settings=settings)
    assert response.headers["X-RateLimit-Limit"] == "2"  # headers on allowed responses (AC3)

    with pytest.raises(RateLimitError) as exc:
        await dep(request, response, user=None, redis=redis, settings=settings)
    assert exc.value.headers is not None
    assert exc.value.headers["X-RateLimit-Remaining"] == "0"  # AC1
    assert int(exc.value.headers["Retry-After"]) > 0


async def test_rate_limit_fails_open_when_redis_errors() -> None:
    class _Raising:
        async def eval(self, *_a: Any, **_k: Any) -> Any:
            raise ConnectionError("redis down")

        async def incr(self, *_a: Any, **_k: Any) -> Any:
            raise ConnectionError("redis down")

    dep = rate_limit(RateLimitPolicy(name="sec-open", limit=1, window_seconds=60, key="ip"))
    # Must NOT raise — the limiter fails open when the backend is unavailable (AC2).
    await dep(_request(), Response(), user=None, redis=_Raising(), settings=get_settings())


# --- CORS (AC6) ------------------------------------------------------------- #


async def test_cors_preflight_allows_configured_origin(async_client: AsyncClient) -> None:
    origin = get_settings().cors_origins[0]
    resp = await async_client.options(
        "/api/v1/projects",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == origin
    assert resp.headers.get("access-control-allow-origin") != "*"
