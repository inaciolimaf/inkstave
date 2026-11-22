"""Rate limits on the routes that had none (auth audit).

Password re-authentication routes (change-email, delete account) share the per-user
password policy; invite routes use the share-link policy; the public first-admin
setup uses the register policy, keyed per IP. Failed attempts count too, so a
wrong-password guess loop is capped.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.accounts.users import normalise_email
from inkstave.modules.auth.credentials.password import build_password_hasher
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User

pytestmark = pytest.mark.integration

PASSWORD = "Sup3rPass"
USERS = "/api/v1/users"
INVITES = "/api/v1/invites"
SETUP = "/api/setup"


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Set the limits the tests need, and reset the settings cache around them."""

    def apply(**values: str) -> None:
        get_settings.cache_clear()
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    yield apply
    get_settings.cache_clear()


async def _user(db: AsyncSession, email: str, *, admin: bool = False) -> User:
    hasher = build_password_hasher(get_settings())
    user = User(
        email=normalise_email(email),
        hashed_password=hasher.hash(PASSWORD),
        display_name="Limited",
        is_admin=admin,
        email_confirmed=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def test_change_email_is_rate_limited_per_user(
    async_client: AsyncClient, db_session: AsyncSession, limits: Any
) -> None:
    limits(RATE_LIMIT_AUTH_PASSWORD="2/3600")
    user = await _user(db_session, "mover@example.com")
    headers = _headers(user)  # before any request: a request commits and expires the row
    body = {"new_email": "new@example.com", "current_password": "wrong-pass1"}

    for _ in range(2):
        r = await async_client.post(f"{USERS}/me/change-email", json=body, headers=headers)
        assert r.status_code == 401
    limited = await async_client.post(f"{USERS}/me/change-email", json=body, headers=headers)

    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "rate_limited"


async def test_delete_account_is_rate_limited_per_user(
    async_client: AsyncClient, db_session: AsyncSession, limits: Any
) -> None:
    limits(RATE_LIMIT_AUTH_PASSWORD="2/3600")
    user = await _user(db_session, "leaver@example.com")
    headers = _headers(user)
    body = {"password": "wrong-pass1", "confirm": True}

    for _ in range(2):
        r = await async_client.request("DELETE", f"{USERS}/me", json=body, headers=headers)
        assert r.status_code == 401
    limited = await async_client.request("DELETE", f"{USERS}/me", json=body, headers=headers)

    assert limited.status_code == 429
    await db_session.refresh(user)
    assert user.is_active is True


async def test_invite_preview_is_rate_limited(
    async_client: AsyncClient, db_session: AsyncSession, limits: Any
) -> None:
    limits(RATE_LIMIT_SHARE_LINK="2/3600")
    user = await _user(db_session, "invitee@example.com")
    headers = _headers(user)

    for _ in range(2):
        assert (await async_client.get(f"{INVITES}/no-such-token", headers=headers)).status_code == 404
    limited = await async_client.get(f"{INVITES}/no-such-token", headers=headers)

    assert limited.status_code == 429


async def test_invite_accept_and_decline_are_rate_limited(
    async_client: AsyncClient, db_session: AsyncSession, limits: Any
) -> None:
    limits(RATE_LIMIT_SHARE_LINK="2/3600")
    user = await _user(db_session, "answerer@example.com")
    headers = _headers(user)

    for _ in range(2):
        assert (
            await async_client.post(f"{INVITES}/no-such-token/decline", headers=headers)
        ).status_code == 404
    limited = await async_client.post(f"{INVITES}/no-such-token/accept", headers=headers)

    assert limited.status_code == 429


async def test_setup_admin_is_rate_limited_per_ip(
    async_client: AsyncClient, db_session: AsyncSession, limits: Any
) -> None:
    # Keyed per IP, so the peer must count: behind an untrusted proxy the limit stands down.
    limits(RATE_LIMIT_REGISTER="2/3600", TRUST_PROXY_HEADERS="true")
    await _user(db_session, "root@example.com", admin=True)
    body = {"email": "intruder@example.com", "password": "Intrud3rPass", "display_name": "X"}

    for _ in range(2):
        assert (await async_client.post(f"{SETUP}/admin", json=body)).status_code == 409
    limited = await async_client.post(f"{SETUP}/admin", json=body)

    assert limited.status_code == 429
    assert limited.json()["error"]["type"] == "rate_limited"
