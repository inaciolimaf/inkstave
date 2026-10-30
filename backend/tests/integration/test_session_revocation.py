"""Ending a session reaches access tokens, not only refresh families."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave import cli
from inkstave.core.config.settings import get_settings
from inkstave.modules.auth import NotAuthenticatedError, authenticate_ws_token, build_token_service, sse_user
from inkstave.modules.auth.accounts.account import deactivate_account
from inkstave.modules.auth.credentials.auth_tokens import issue_token
from inkstave.modules.auth.credentials.sessions import end_every_session, revoke_session
from inkstave.modules.auth.models.revoked_session import RevokedSession
from inkstave.modules.auth.models.user import User

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/users/me"
PASSWORD = "secret123"
EMAIL = "session@example.com"


async def _login(client: AsyncClient) -> dict[str, Any]:
    response = await client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


async def _account(client: AsyncClient) -> dict[str, Any]:
    body = {"email": EMAIL, "password": PASSWORD, "display_name": "User"}
    assert (await client.post(REGISTER, json=body)).status_code == 201
    return await _login(client)


async def _me(client: AsyncClient, pair: dict[str, Any]) -> int:
    headers = {"Authorization": f"Bearer {pair['access_token']}"}
    return (await client.get(ME, headers=headers)).status_code


async def _refresh(client: AsyncClient, pair: dict[str, Any]) -> Any:
    return await client.post(REFRESH, json={"refresh_token": pair["refresh_token"]})


async def _user(session: AsyncSession) -> User:
    return await session.scalar(select(User).where(User.email == EMAIL))  # type: ignore[return-value]


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def _legacy_access(user: User) -> str:
    """An access token as issued before ``sv`` and ``sid`` existed."""
    settings = get_settings()
    now = datetime.now(tz=UTC)
    claims = {
        "sub": str(user.id),
        "type": "access",
        "is_admin": False,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl_seconds),
        "jti": uuid4().hex,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _legacy_refresh(user: User, family_id: str, jti: str) -> str:
    settings = get_settings()
    now = datetime.now(tz=UTC)
    claims = {
        "sub": str(user.id),
        "type": "refresh",
        "family_id": family_id,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_token_ttl_seconds),
        "jti": jti,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def test_logout_kills_the_copied_access_token(async_client: AsyncClient) -> None:
    pair = await _account(async_client)
    assert await _me(async_client, pair) == 200

    assert (await async_client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})).status_code == 200

    assert await _me(async_client, pair) == 401
    assert (await _refresh(async_client, pair)).status_code == 401


async def test_logout_leaves_other_devices_signed_in(async_client: AsyncClient) -> None:
    this_device = await _account(async_client)
    other_device = await _login(async_client)

    await async_client.post(LOGOUT, json={"refresh_token": this_device["refresh_token"]})

    assert await _me(async_client, other_device) == 200
    assert (await _refresh(async_client, other_device)).status_code == 200


async def test_logout_after_a_refresh_still_kills_the_first_access_token(async_client: AsyncClient) -> None:
    first = await _account(async_client)
    second = (await _refresh(async_client, first)).json()
    assert _claims(second["access_token"])["sid"] == _claims(first["access_token"])["sid"]

    await async_client.post(LOGOUT, json={"refresh_token": second["refresh_token"]})

    assert await _me(async_client, first) == 401
    assert await _me(async_client, second) == 401


async def test_logging_out_twice_is_idempotent(async_client: AsyncClient) -> None:
    pair = await _account(async_client)
    for _ in range(2):
        response = await async_client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})
        assert response.status_code == 200


async def test_logout_sweeps_expired_rows(async_client: AsyncClient, db_session: AsyncSession) -> None:
    pair = await _account(async_client)
    db_session.add(RevokedSession(session_id=uuid4(), expires_at=datetime.now(tz=UTC) - timedelta(days=1)))
    await db_session.flush()

    await async_client.post(LOGOUT, json={"refresh_token": pair["refresh_token"]})

    assert await db_session.scalar(select(func.count()).select_from(RevokedSession)) == 1


async def test_change_password_kills_every_access_token(async_client: AsyncClient) -> None:
    pair = await _account(async_client)
    other_device = await _login(async_client)
    response = await async_client.post(
        f"{ME}/change-password",
        json={"current_password": PASSWORD, "new_password": "FreshSecret9"},
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )
    assert response.status_code == 200

    assert await _me(async_client, pair) == 401
    assert await _me(async_client, other_device) == 401
    assert (await _refresh(async_client, other_device)).status_code == 401


async def test_password_reset_kills_every_access_token(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    pair = await _account(async_client)
    user = await _user(db_session)
    issued = await issue_token(
        db_session, user_id=user.id, email=user.email, purpose="password_reset", ttl_seconds=600
    )
    await db_session.flush()
    response = await async_client.post(
        "/api/v1/auth/reset-password", json={"token": issued.raw, "new_password": "FreshSecret9"}
    )
    assert response.status_code == 200

    assert await _me(async_client, pair) == 401


async def test_deactivation_ends_access_refresh_and_login(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    pair = await _account(async_client)
    await deactivate_account(db_session, await _user(db_session))
    await db_session.commit()  # the 401s below roll back whatever is still pending

    assert await _me(async_client, pair) == 401
    assert (await _refresh(async_client, pair)).status_code == 401
    body = {"email": EMAIL, "password": PASSWORD}
    assert (await async_client.post(LOGIN, json=body)).status_code == 401


async def test_deactivated_account_cannot_use_a_magic_link(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _account(async_client)
    user = await _user(db_session)
    issued = await issue_token(
        db_session, user_id=user.id, email=user.email, purpose="magic_login", ttl_seconds=600
    )
    await deactivate_account(db_session, user)

    response = await async_client.post("/api/v1/auth/magic-link/callback", json={"token": issued.raw})

    assert response.status_code == 400


async def test_is_active_alone_is_enough_to_refuse_a_token(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    pair = await _account(async_client)
    (await _user(db_session)).is_active = False
    await db_session.flush()

    assert await _me(async_client, pair) == 401


async def test_cli_deactivates_by_email(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = await _account(async_client)

    class _Sessions:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *_: object) -> None:
            await db_session.flush()

    class _Engine:
        async def dispose(self) -> None:
            return None

    monkeypatch.setattr(cli, "create_engine_and_sessionmaker", lambda _s: (_Engine(), _Sessions))

    assert await cli._cmd_deactivate_user("nobody@example.com") == 1
    assert await cli._cmd_deactivate_user(EMAIL) == 0
    assert await _me(async_client, pair) == 401


async def test_pre_deploy_tokens_keep_working_until_the_version_moves(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _account(async_client)
    user = await _user(db_session)
    legacy = {"access_token": _legacy_access(user)}
    assert await _me(async_client, legacy) == 200

    end_every_session(user)
    await db_session.flush()

    assert await _me(async_client, legacy) == 401


async def test_pre_deploy_refresh_token_rotates_into_the_new_claims(
    async_client: AsyncClient, db_session: AsyncSession, app: Any
) -> None:
    pair = await _account(async_client)
    user = await _user(db_session)
    original = _claims(pair["refresh_token"])
    legacy = {"refresh_token": _legacy_refresh(user, original["family_id"], original["jti"])}

    response = await _refresh(async_client, legacy)

    assert response.status_code == 200
    rotated = _claims(response.json()["access_token"])
    assert rotated["sid"] == original["family_id"]
    assert rotated["sv"] == 0


async def test_websocket_and_sse_paths_refuse_a_revoked_session(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    pair = await _account(async_client)
    token_service = build_token_service(get_settings())
    token = pair["access_token"]
    assert await authenticate_ws_token(token, token_service, db_session)
    assert await sse_user(token, None, token_service, db_session)

    await revoke_session(db_session, _claims(token)["sid"], ttl_seconds=60)

    with pytest.raises(NotAuthenticatedError):
        await authenticate_ws_token(token, token_service, db_session)
    with pytest.raises(NotAuthenticatedError):
        await sse_user(token, None, token_service, db_session)
