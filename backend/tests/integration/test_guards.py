"""Integration tests for the auth guards, /users/me, admin gate and rate limit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.dependencies import (
    NotAuthenticatedError,
    authenticate_ws_token,
    get_optional_user,
)
from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.user import User
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

ME = "/api/v1/users/me"
ADMIN_PING = "/api/v1/admin/ping"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


def _access_token_for(user: User) -> str:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return token


def _craft_access_token(*, sub: str, is_admin: bool, expired: bool = False) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(minutes=5)
    return jwt.encode(
        {
            "sub": sub,
            "type": "access",
            "is_admin": is_admin,
            "iat": now - timedelta(minutes=2),
            "exp": exp,
            "jti": uuid4().hex,
            "iss": settings.jwt_issuer,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_user(db_session: AsyncSession, *, is_admin: bool = False) -> User:
    user = await UserFactory.create(db_session, is_admin=is_admin)
    await db_session.commit()
    return user


# --- /users/me ----------------------------------------------------------- #


async def test_me_with_valid_token(async_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    resp = await async_client.get(ME, headers=_auth(_access_token_for(user)))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(user.id)
    assert body["email"] == user.email
    assert "hashed_password" not in body


async def test_me_without_token_is_401_with_challenge(async_client: AsyncClient) -> None:
    resp = await async_client.get(ME)
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_me_with_malformed_token_is_401(async_client: AsyncClient) -> None:
    resp = await async_client.get(ME, headers=_auth("not-a-jwt"))
    assert resp.status_code == 401


async def test_me_with_expired_token_is_401(async_client: AsyncClient) -> None:
    token = _craft_access_token(sub=str(uuid4()), is_admin=False, expired=True)
    resp = await async_client.get(ME, headers=_auth(token))
    assert resp.status_code == 401


async def test_me_with_unknown_user_is_401(async_client: AsyncClient) -> None:
    # Valid signature, but the sub references no user.
    token = _craft_access_token(sub=str(uuid4()), is_admin=False)
    resp = await async_client.get(ME, headers=_auth(token))
    assert resp.status_code == 401


# --- admin gate ---------------------------------------------------------- #


async def test_admin_ping_allows_admin(async_client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _seed_user(db_session, is_admin=True)
    resp = await async_client.get(ADMIN_PING, headers=_auth(_access_token_for(admin)))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_admin_ping_rejects_non_admin(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _seed_user(db_session, is_admin=False)
    resp = await async_client.get(ADMIN_PING, headers=_auth(_access_token_for(user)))
    assert resp.status_code == 403
    assert resp.json()["error"]["message"] == "Admin privileges required."


async def test_admin_check_is_db_authoritative(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # DB says not admin, but the token claims is_admin=true -> still 403.
    user = await _seed_user(db_session, is_admin=False)
    token = _craft_access_token(sub=str(user.id), is_admin=True)
    resp = await async_client.get(ADMIN_PING, headers=_auth(token))
    assert resp.status_code == 403


# --- optional auth ------------------------------------------------------- #


async def test_optional_auth_route(app: Any, async_client: AsyncClient) -> None:
    async def whoami(user: User | None = Depends(get_optional_user)) -> dict[str, str | None]:
        return {"user": str(user.id) if user else None}

    app.add_api_route("/_test/whoami", whoami, methods=["GET"])

    anon = await async_client.get("/_test/whoami")
    assert anon.status_code == 200
    assert anon.json()["user"] is None

    invalid = await async_client.get("/_test/whoami", headers=_auth("garbage"))
    assert invalid.status_code == 401


# --- WS auth helper ------------------------------------------------------ #


async def test_authenticate_ws_token(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    service = build_token_service(get_settings())
    token, _ = service.create_access_token(user)

    resolved = await authenticate_ws_token(token, service, db_session)
    assert resolved.id == user.id

    with pytest.raises(NotAuthenticatedError):
        await authenticate_ws_token("garbage", service, db_session)

    expired = _craft_access_token(sub=str(user.id), is_admin=False, expired=True)
    with pytest.raises(NotAuthenticatedError):
        await authenticate_ws_token(expired, service, db_session)


# --- revocation chain (spec 07 + 08) ------------------------------------- #


async def test_revoked_family_cannot_mint_access(
    async_client: AsyncClient,
) -> None:
    reg = {"email": "chain@example.com", "password": "secret123", "display_name": "Chain"}
    assert (await async_client.post("/api/v1/auth/register", json=reg)).status_code == 201
    pair1 = (
        await async_client.post(LOGIN, json={"email": reg["email"], "password": reg["password"]})
    ).json()

    # Access token works on a protected route.
    assert (await async_client.get(ME, headers=_auth(pair1["access_token"]))).status_code == 200

    # Rotate, then replay the old refresh -> reuse -> family revoked.
    pair2 = (
        await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    ).json()
    replay = await async_client.post(REFRESH, json={"refresh_token": pair1["refresh_token"]})
    assert replay.status_code == 401

    # No usable access token can be minted from the revoked family.
    after = await async_client.post(REFRESH, json={"refresh_token": pair2["refresh_token"]})
    assert after.status_code == 401


# --- rate limiting ------------------------------------------------------- #


async def test_login_rate_limit_returns_429(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "2/300")

    payload = {"email": "throttle@example.com", "password": "whatever1"}
    assert (await async_client.post(LOGIN, json=payload)).status_code == 401  # 1
    assert (await async_client.post(LOGIN, json=payload)).status_code == 401  # 2
    third = await async_client.post(LOGIN, json=payload)  # 3 -> limited
    assert third.status_code == 429
    assert third.headers.get("retry-after") is not None
    assert third.json()["error"]["type"] == "rate_limited"
