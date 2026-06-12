"""Integration tests for login / refresh / logout (spec 07)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.config import get_settings

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


async def _register(
    client: AsyncClient,
    email: str = "user@example.com",
    password: str = "secret123",
) -> tuple[str, str]:
    resp = await client.post(
        REGISTER, json={"email": email, "password": password, "display_name": "User"}
    )
    assert resp.status_code == 201
    return email, password


async def _login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


async def test_login_success_returns_token_pair(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    body = await _login(async_client, email, password)
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == get_settings().access_token_ttl_seconds


async def test_access_token_claims(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    body = await _login(async_client, email, password)
    settings = get_settings()
    claims = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
    )
    assert claims["type"] == "access"
    assert claims["is_admin"] is False
    UUID(claims["sub"])  # sub is a valid UUID
    assert claims["exp"] - claims["iat"] == settings.access_token_ttl_seconds


async def test_login_failures_are_uniform(async_client: AsyncClient) -> None:
    email, _ = await _register(async_client)
    wrong_pw = await async_client.post(LOGIN, json={"email": email, "password": "wrongpass1"})
    unknown = await async_client.post(
        LOGIN, json={"email": "nobody@example.com", "password": "whatever1"}
    )
    assert wrong_pw.status_code == 401
    assert unknown.status_code == 401
    assert (
        wrong_pw.json()["error"]["message"]
        == unknown.json()["error"]["message"]
        == "Invalid email or password."
    )


async def test_refresh_rotates_tokens(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    pair1 = await _login(async_client, email, password)

    r2 = await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    assert r2.status_code == 200
    pair2 = r2.json()
    assert pair2["refresh_token"] != pair1["refresh_token"]
    assert pair2["access_token"]

    # The newly issued refresh token works on a subsequent refresh.
    r3 = await async_client.post(REFRESH, json={"refresh_token": pair2["refresh_token"]})
    assert r3.status_code == 200

    # The original (rotated) refresh token is now rejected.
    old = await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    assert old.status_code == 401


async def test_refresh_reuse_revokes_family(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    pair1 = await _login(async_client, email, password)

    pair2 = (
        await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    ).json()

    # Replay the already-rotated token -> reuse detected.
    replay = await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    assert replay.status_code == 401
    assert "reuse detected" in replay.json()["error"]["message"].lower()

    # The whole family is now revoked: even the latest refresh token is rejected.
    after = await async_client.post(REFRESH, json={"refresh_token": pair2["refresh_token"]})
    assert after.status_code == 401


async def test_refresh_with_expired_token(async_client: AsyncClient) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",
            "family_id": str(uuid4()),
            "jti": uuid4().hex,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "iss": settings.jwt_issuer,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    resp = await async_client.post(REFRESH, json={"refresh_token": expired})
    assert resp.status_code == 401


async def test_refresh_with_tampered_token(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    pair = await _login(async_client, email, password)
    tampered = pair["refresh_token"][:-2] + ("aa" if pair["refresh_token"][-1] != "a" else "bb")
    resp = await async_client.post(REFRESH, json={"refresh_token": tampered})
    assert resp.status_code == 401


async def test_refresh_with_deleted_user_is_401(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    email, password = await _register(async_client)
    pair = await _login(async_client, email, password)

    # The account is removed after the refresh token was issued.
    await db_session.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    await db_session.commit()

    resp = await async_client.post(REFRESH, json={"refresh_token": pair["refresh_token"]})
    assert resp.status_code == 401


async def test_logout_with_invalid_token_is_idempotent(async_client: AsyncClient) -> None:
    resp = await async_client.post(LOGOUT, json={"refresh_token": "not-a-valid-jwt"})
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Logged out."


async def test_logout_is_idempotent_and_revokes(async_client: AsyncClient) -> None:
    email, password = await _register(async_client)
    pair = await _login(async_client, email, password)

    first = await async_client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})
    assert first.status_code == 200
    assert first.json()["detail"] == "Logged out."

    # Refresh after logout is rejected (family revoked).
    refreshed = await async_client.post(REFRESH, json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 401

    # Logging out again is still 200.
    second = await async_client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})
    assert second.status_code == 200


@pytest.mark.parametrize(
    ("url", "payload"),
    [
        (LOGIN, {"email": "user@example.com"}),  # missing password
        (LOGIN, {"email": "not-an-email", "password": "secret123"}),  # bad email
        (REFRESH, {}),  # missing refresh_token
        (REFRESH, {"refresh_token": 123}),  # non-string
        (LOGOUT, {}),  # missing refresh_token
    ],
)
async def test_auth_validation_errors(
    async_client: AsyncClient, url: str, payload: dict[str, object]
) -> None:
    resp = await async_client.post(url, json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"
