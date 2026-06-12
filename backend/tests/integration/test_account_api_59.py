"""Spec-59 integration tests: profile, editor preferences, change-password,
change-email + confirm, and account deletion — HTTP against the test DB with a
fake email enqueuer and fake Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import build_password_hasher
from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.user import User
from inkstave.dependencies import get_email_enqueuer
from inkstave.services.user import normalise_email

pytestmark = pytest.mark.integration

USERS = "/api/v1/users"
PASSWORD = "Sup3rPass"


class FakeEmailEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        self.calls.append({"template": template, "to": to, "context": context})
        return "job-1"


@pytest.fixture
def enqueuer(app: Any) -> FakeEmailEnqueuer:
    fake = FakeEmailEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: fake
    return fake


async def _user(
    db: AsyncSession, *, email: str = "owner@example.com", password: str = PASSWORD
) -> User:
    hasher = build_password_hasher(get_settings())
    user = User(
        email=normalise_email(email), hashed_password=hasher.hash(password), display_name="Owner"
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


# --- profile + preferences --------------------------------------------------- #


async def test_get_and_patch_profile(async_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _user(db_session)
    h = _headers(user)

    me = await async_client.get(f"{USERS}/me", headers=h)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@example.com" and body["avatar_url"] is None
    assert body["editor_preferences"] == {"theme": "system", "font_size": 14, "keymap": "default"}

    patched = await async_client.patch(
        f"{USERS}/me", json={"display_name": "  New Name  "}, headers=h
    )
    assert patched.status_code == 200 and patched.json()["display_name"] == "New Name"
    assert (await async_client.get(f"{USERS}/me", headers=h)).json()["display_name"] == "New Name"


async def test_editor_preferences_round_trip_and_clamp(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    h = _headers(await _user(db_session))
    r = await async_client.put(
        f"{USERS}/me/editor-preferences",
        json={"theme": "dark", "font_size": 99, "keymap": "vim"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json() == {"theme": "dark", "font_size": 28, "keymap": "vim"}  # font clamped to 28
    # Persisted + returned on the next read.
    assert (await async_client.get(f"{USERS}/me", headers=h)).json()["editor_preferences"][
        "theme"
    ] == "dark"
    # Bad enum → 422.
    bad = await async_client.put(
        f"{USERS}/me/editor-preferences", json={"keymap": "nano"}, headers=h
    )
    assert bad.status_code == 422


# --- change password --------------------------------------------------------- #


async def test_change_password_success_and_revokes_sessions(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session, email="pw@example.com")
    # A live session (refresh token) that must be revoked by the change.
    login = await async_client.post(
        "/api/v1/auth/login", json={"email": "pw@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    r = await async_client.post(
        f"{USERS}/me/change-password",
        json={"current_password": PASSWORD, "new_password": "FreshSecret9"},
        headers=_headers(user),
    )
    assert r.status_code == 200

    # New password logs in; old one fails.
    assert (
        await async_client.post(
            "/api/v1/auth/login", json={"email": "pw@example.com", "password": "FreshSecret9"}
        )
    ).status_code == 200
    assert (
        await async_client.post(
            "/api/v1/auth/login", json={"email": "pw@example.com", "password": PASSWORD}
        )
    ).status_code == 401
    # The pre-existing refresh token is now revoked.
    assert (
        await async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    ).status_code == 401


async def test_change_password_wrong_current_is_rejected(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session)
    r = await async_client.post(
        f"{USERS}/me/change-password",
        json={"current_password": "WrongOne1", "new_password": "FreshSecret9"},
        headers=_headers(user),
    )
    assert r.status_code == 401
    await db_session.refresh(user)
    # Nothing changed: the original password still verifies.
    assert build_password_hasher(get_settings()).verify(PASSWORD, user.hashed_password)


# --- change email + confirm -------------------------------------------------- #


async def test_change_email_then_confirm(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEmailEnqueuer
) -> None:
    user = await _user(db_session, email="old@example.com")
    h = _headers(user)

    started = await async_client.post(
        f"{USERS}/me/change-email",
        json={"new_email": "new@example.com", "current_password": PASSWORD},
        headers=h,
    )
    assert started.status_code == 202
    # A confirmation was enqueued to the NEW address; the active email is unchanged.
    assert enqueuer.calls[-1]["template"] == "email_change_confirmation"
    assert enqueuer.calls[-1]["to"] == "new@example.com"
    await db_session.refresh(user)
    assert user.email == "old@example.com" and user.pending_email == "new@example.com"
    assert user.email_change_token_hash is not None

    token = enqueuer.calls[-1]["context"]["confirm_url"].split("token=", 1)[1]
    confirmed = await async_client.post(f"{USERS}/confirm-email-change", json={"token": token})
    assert confirmed.status_code == 200 and confirmed.json()["email"] == "new@example.com"
    await db_session.refresh(user)
    assert user.email == "new@example.com" and user.pending_email is None

    # Single-use: the same token cannot be replayed.
    replay = await async_client.post(f"{USERS}/confirm-email-change", json={"token": token})
    assert replay.status_code == 400


async def test_change_email_to_existing_address_conflicts(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="taken@example.com")
    me = await _user(db_session, email="me@example.com")
    r = await async_client.post(
        f"{USERS}/me/change-email",
        json={"new_email": "taken@example.com", "current_password": PASSWORD},
        headers=_headers(me),
    )
    assert r.status_code == 409
    assert enqueuer.calls == []  # nothing sent


async def test_confirm_expired_token_is_gone(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeEmailEnqueuer
) -> None:
    user = await _user(db_session, email="exp@example.com")
    await async_client.post(
        f"{USERS}/me/change-email",
        json={"new_email": "later@example.com", "current_password": PASSWORD},
        headers=_headers(user),
    )
    token = enqueuer.calls[-1]["context"]["confirm_url"].split("token=", 1)[1]
    # Force the token to have already expired.
    await db_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(email_change_expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db_session.commit()
    r = await async_client.post(f"{USERS}/confirm-email-change", json={"token": token})
    assert r.status_code == 410


# --- account deletion -------------------------------------------------------- #


async def test_delete_account_cascades_and_revokes(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session, email="bye@example.com")
    h = _headers(user)
    # Give the user a project (must cascade away).
    pr = await async_client.post("/api/v1/projects", json={"name": "Gone"}, headers=h)
    assert pr.status_code == 201

    deleted = await async_client.request(
        "DELETE", f"{USERS}/me", json={"password": PASSWORD, "confirm": True}, headers=h
    )
    assert deleted.status_code == 204

    # The row (and its project) are gone; further authed requests 401 (user lookup fails).
    assert (
        await db_session.scalar(select(func.count()).select_from(User).where(User.id == user.id))
        == 0
    )
    assert (await async_client.get(f"{USERS}/me", headers=h)).status_code == 401


async def test_delete_requires_confirm_and_correct_password(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _user(db_session)
    h = _headers(user)
    assert (
        await async_client.request(
            "DELETE", f"{USERS}/me", json={"password": PASSWORD, "confirm": False}, headers=h
        )
    ).status_code == 422
    assert (
        await async_client.request(
            "DELETE", f"{USERS}/me", json={"password": "nope1234", "confirm": True}, headers=h
        )
    ).status_code == 401


# --- authz ------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("GET", f"{USERS}/me", None),
        ("PATCH", f"{USERS}/me", {"display_name": "x"}),
        ("PUT", f"{USERS}/me/editor-preferences", {"theme": "dark"}),
        (
            "POST",
            f"{USERS}/me/change-password",
            {"current_password": "a", "new_password": "Abcd1234"},
        ),
        ("POST", f"{USERS}/me/change-email", {"new_email": "a@b.com", "current_password": "a"}),
        ("DELETE", f"{USERS}/me", {"password": "a", "confirm": True}),
    ],
)
async def test_endpoints_require_auth(
    async_client: AsyncClient, method: str, path: str, body: dict[str, Any] | None
) -> None:
    r = await async_client.request(method, path, json=body)
    assert r.status_code == 401
