"""Integration tests for middleware, exception handlers, CORS and OpenAPI."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from inkstave.app import create_app
from inkstave.config import get_settings
from inkstave.errors import NotFoundError

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
