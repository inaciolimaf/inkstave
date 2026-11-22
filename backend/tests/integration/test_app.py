"""Integration tests for middleware, exception handlers, CORS and OpenAPI."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from inkstave.app import create_app
from inkstave.core.config.settings import get_settings
from inkstave.core.errors import NotFoundError

pytestmark = pytest.mark.integration


def _attach_error_routes(app: Any) -> None:
    async def raise_not_found() -> None:
        raise NotFoundError("Document 42 not found")

    async def raise_boom() -> None:
        raise RuntimeError("kaboom: secret stack detail")

    async def needs_param(x: int) -> dict[str, int]:
        return {"x": x}

    app.add_api_route("/_test/not-found", raise_not_found, methods=["GET"])
    app.add_api_route("/_test/boom", raise_boom, methods=["GET"])
    app.add_api_route("/_test/validate", needs_param, methods=["GET"])

    async def echo(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    app.add_api_route("/_test/echo", echo, methods=["POST"])


async def test_validation_error_envelope(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    resp = await async_client.get("/_test/validate")  # missing required ?x=
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["type"] == "validation_error"
    assert body["error"]["details"]
    assert body["error"]["request_id"]


async def test_not_found_envelope(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    resp = await async_client.get("/_test/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["type"] == "not_found"
    assert body["error"]["message"] == "Document 42 not found"


async def test_internal_error_hides_traceback(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    resp = await async_client.get("/_test/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["type"] == "internal_error"
    assert body["error"]["message"] == "Internal server error"
    assert "secret stack detail" not in resp.text


async def test_request_id_generated_and_echoed(async_client: AsyncClient) -> None:
    header = get_settings().request_id_header
    resp = await async_client.get("/health")
    generated = resp.headers.get(header)
    assert generated and len(generated) >= 16

    resp2 = await async_client.get("/health", headers={header: "provided-id-123"})
    assert resp2.headers.get(header) == "provided-id-123"


async def test_error_response_carries_request_id(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    header = get_settings().request_id_header
    resp = await async_client.get("/_test/not-found", headers={header: "rid-xyz"})
    assert resp.headers.get(header) == "rid-xyz"
    assert resp.json()["error"]["request_id"] == "rid-xyz"


async def test_openapi_documents_error_envelope(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    schemas = resp.json()["components"]["schemas"]
    assert "ErrorEnvelope" in schemas
    assert "ErrorBody" in schemas


async def test_cors_preflight_allowed_origin(async_client: AsyncClient) -> None:
    resp = await async_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_cors_preflight_disallowed_origin(async_client: AsyncClient) -> None:
    resp = await async_client.options(
        "/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") is None


async def test_internal_error_includes_class_name_in_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    # In DEBUG, the 500 message appends the exception class name (local aid).
    get_settings.cache_clear()
    monkeypatch.setenv("DEBUG", "true")
    app = create_app()

    async def boom() -> None:
        raise ValueError("inner detail")

    app.add_api_route("/_test/boom-debug", boom, methods=["GET"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/_test/boom-debug")
    assert resp.status_code == 500
    message = resp.json()["error"]["message"]
    assert "ValueError" in message
    assert "inner detail" not in resp.text  # the message text still never leaks


async def test_docs_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    # Built without the DB-wired `app` fixture: create_app opens no connections.
    get_settings.cache_clear()
    monkeypatch.setenv("DOCS_ENABLED", "true")
    enabled = create_app()
    async with AsyncClient(transport=ASGITransport(app=enabled), base_url="http://test") as c:
        assert (await c.get("/docs")).status_code == 200

    get_settings.cache_clear()
    monkeypatch.setenv("DOCS_ENABLED", "false")
    disabled = create_app()
    async with AsyncClient(transport=ASGITransport(app=disabled), base_url="http://test") as c:
        assert (await c.get("/docs")).status_code == 404


async def test_unhandled_error_carries_request_id_and_headers(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    header = get_settings().request_id_header
    resp = await async_client.get(
        "/_test/boom", headers={header: "rid-500", "Origin": "http://localhost:5173"}
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["request_id"] == "rid-500"
    assert resp.headers.get(header) == "rid-500"
    assert resp.headers.get("x-frame-options") == "DENY"  # security headers reach the 500
    assert resp.headers.get("content-security-policy")
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"  # CORS too


async def test_unknown_route_404_uses_the_envelope(async_client: AsyncClient) -> None:
    resp = await async_client.get("/_test/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["type"] == "not_found"
    assert body["error"]["request_id"]


async def test_wrong_method_405_uses_the_envelope_and_keeps_allow(async_client: AsyncClient) -> None:
    resp = await async_client.post("/health")
    assert resp.status_code == 405
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["type"] == "method_not_allowed"
    assert "GET" in resp.headers.get("allow", "")


async def test_body_limit_413_uses_the_envelope_with_request_id(app: Any, async_client: AsyncClient) -> None:
    _attach_error_routes(app)
    header = get_settings().request_id_header
    too_big = b"x" * (get_settings().max_request_body_bytes + 1)
    resp = await async_client.post(
        "/_test/echo", content=too_big, headers={header: "rid-413", "Origin": "http://localhost:5173"}
    )
    assert resp.status_code == 413
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["type"] == "payload_too_large"
    assert body["error"]["request_id"] == "rid-413"
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
