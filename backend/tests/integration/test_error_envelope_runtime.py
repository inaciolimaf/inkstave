"""Runtime error-surface verification (spec 61).

Locks down the uniform error envelope across the representative status codes
(401/403/404/409/422 from real endpoints; 413 service error and 500 via
test-only routes) and proves the 500 handler never leaks internals. No
behavioural change — verification only.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi import APIRouter
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.services.document_service import ContentTooLargeError
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

_LEAK = "super-secret-internal-detail-do-not-leak"


def _assert_envelope(
    body: dict[str, Any], *, expect_type: str | None = None, require_request_id: bool = True
) -> None:
    """Assert ``body`` matches ``ErrorEnvelope`` ``{error: {type, message, ...}}``.

    ``require_request_id`` is relaxed for the 500 path: Starlette routes the
    catch-all ``Exception`` handler through ``ServerErrorMiddleware``, which sits
    *outside* ``RequestContextMiddleware``, so the request-id context is already
    unwound when the body is built. The representative typed errors below still
    carry a non-empty request id.
    """
    assert set(body.keys()) == {"error"}, body
    err = body["error"]
    assert isinstance(err["type"], str) and err["type"]
    assert isinstance(err["message"], str) and err["message"]
    assert "details" in err  # key always present (may be null)
    assert "request_id" in err
    if require_request_id:
        assert isinstance(err["request_id"], str) and err["request_id"]
    if expect_type is not None:
        assert err["type"] == expect_type


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def test_401_envelope(async_client: AsyncClient) -> None:
    r = await async_client.get("/api/v1/admin/ping")
    assert r.status_code == 401
    _assert_envelope(r.json(), expect_type="unauthorized")


async def test_403_envelope(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # A non-admin user hitting the admin-only ping is forbidden.
    r = await async_client.get("/api/v1/admin/ping", headers=await _auth(db_session))
    assert r.status_code == 403
    _assert_envelope(r.json(), expect_type="forbidden")


async def test_404_envelope(async_client: AsyncClient, db_session: AsyncSession) -> None:
    r = await async_client.get(f"/api/v1/projects/{uuid4()}", headers=await _auth(db_session))
    assert r.status_code == 404
    # `project_not_found` is a `NotFoundError` subclass — still the uniform envelope.
    _assert_envelope(r.json(), expect_type="project_not_found")


async def test_409_envelope(async_client: AsyncClient) -> None:
    payload = {
        "email": "dupe@example.com",
        "password": "Str0ng-Passw0rd!",
        "display_name": "Dupe",
    }
    first = await async_client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await async_client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    _assert_envelope(second.json(), expect_type="conflict")


async def test_422_envelope_has_details(async_client: AsyncClient) -> None:
    r = await async_client.post("/api/v1/auth/register", json={})
    assert r.status_code == 422
    body = r.json()
    _assert_envelope(body, expect_type="validation_error")
    assert isinstance(body["error"]["details"], list) and body["error"]["details"]


async def test_413_service_error_envelope(app: Any, async_client: AsyncClient) -> None:
    # Service-level 413s (ContentTooLargeError/FileTooLargeError) flow through the
    # AppError handler and DO carry the uniform envelope (the history *diff* 413 is
    # the documented exception — covered separately in test_history_api.py).
    router = APIRouter()

    @router.get("/__test__/too-large")
    async def _too_large() -> None:
        raise ContentTooLargeError()

    app.include_router(router)
    r = await async_client.get("/__test__/too-large")
    assert r.status_code == 413
    _assert_envelope(r.json(), expect_type="content_too_large")


async def test_500_envelope_does_not_leak_internals(app: Any, async_client: AsyncClient) -> None:
    router = APIRouter()

    @router.get("/__test__/boom")
    async def _boom() -> None:
        raise RuntimeError(_LEAK)

    app.include_router(router)
    r = await async_client.get("/__test__/boom")
    assert r.status_code == 500
    body = r.json()
    _assert_envelope(body, expect_type="internal_error", require_request_id=False)
    # The internal exception text and any traceback must never reach the client.
    assert _LEAK not in r.text
    assert "Traceback" not in r.text
