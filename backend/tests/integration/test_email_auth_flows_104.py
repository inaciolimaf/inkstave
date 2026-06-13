"""Integration tests for the spec-104 email link flows (verify / magic / reset).

HTTP against the test DB with a capturing fake email enqueuer and fake Redis —
no real email, no worker, no socket. Token expiry is forced by editing the
persisted ``expires_at`` (no real waiting). Non-enumeration, single-use, and
session revocation are all asserted end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import build_password_hasher
from inkstave.config import get_settings
from inkstave.db.models.auth_token import AuthToken
from inkstave.db.models.user import User
from inkstave.dependencies import get_email_enqueuer
from inkstave.services.user import normalise_email

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
PASSWORD = "Sup3rPass"


class FakeEmailEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        self.calls.append({"template": template, "to": to, "context": context})
        return "job"


@pytest.fixture
def emails(app: Any) -> FakeEmailEnqueuer:
    fake = FakeEmailEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: fake
    return fake


async def _user(
    db: AsyncSession, *, email: str = "owner@example.com", confirmed: bool = False
) -> User:
    hasher = build_password_hasher(get_settings())
    user = User(
        email=normalise_email(email),
        hashed_password=hasher.hash(PASSWORD),
        display_name="Owner",
        email_confirmed=confirmed,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _token_from(call: dict[str, Any], url_key: str) -> str:
    url = call["context"][url_key]
    return url.split("token=", 1)[1]


async def _expire_all(db: AsyncSession) -> None:
    """Force every outstanding token into the past (drives the 410 path)."""
    await db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()


# --- email verification ---------------------------------------------------- #


async def test_register_enqueues_one_verification_with_real_token(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    resp = await async_client.post(
        f"{AUTH}/register",
        json={"email": "alice@example.com", "password": PASSWORD, "display_name": "Alice"},
    )
    assert resp.status_code == 201, resp.text
    assert len(emails.calls) == 1
    call = emails.calls[0]
    assert call["template"] == "email_verification"
    assert call["to"] == "alice@example.com"
    assert "/verify-email?token=" in call["context"]["verify_url"]
    # The token is persisted (a real row), not a throwaway.
    row = await db_session.scalar(select(AuthToken).where(AuthToken.purpose == "email_verify"))
    assert row is not None and row.consumed_at is None


async def test_verify_confirm_then_replay_then_expired(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await async_client.post(
        f"{AUTH}/register",
        json={"email": "bob@example.com", "password": PASSWORD, "display_name": "Bob"},
    )
    raw = _token_from(emails.calls[0], "verify_url")

    ok = await async_client.post(f"{AUTH}/verify-email/confirm", json={"token": raw})
    assert ok.status_code == 200, ok.text
    assert ok.json()["email_confirmed"] is True

    # Replay → 400 (single-use).
    replay = await async_client.post(f"{AUTH}/verify-email/confirm", json={"token": raw})
    assert replay.status_code == 400

    # Unknown token → 400.
    unknown = await async_client.post(f"{AUTH}/verify-email/confirm", json={"token": "nope"})
    assert unknown.status_code == 400


async def test_verify_expired_returns_410(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await async_client.post(
        f"{AUTH}/register",
        json={"email": "exp@example.com", "password": PASSWORD, "display_name": "Exp"},
    )
    raw = _token_from(emails.calls[0], "verify_url")
    await _expire_all(db_session)
    gone = await async_client.post(f"{AUTH}/verify-email/confirm", json={"token": raw})
    assert gone.status_code == 410


async def test_resend_confirmed_user_enqueues_zero(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="conf@example.com", confirmed=True)
    resp = await async_client.post(
        f"{AUTH}/verify-email/resend", json={"email": "conf@example.com"}
    )
    assert resp.status_code == 202
    assert emails.calls == []  # already confirmed → silent, no spam


async def test_resend_unknown_user_enqueues_zero(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    resp = await async_client.post(f"{AUTH}/verify-email/resend", json={"email": "ghost@x.com"})
    assert resp.status_code == 202
    assert emails.calls == []


async def test_resend_unconfirmed_enqueues_one(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="unconf@example.com", confirmed=False)
    resp = await async_client.post(
        f"{AUTH}/verify-email/resend", json={"email": "unconf@example.com"}
    )
    assert resp.status_code == 202
    assert len(emails.calls) == 1
    assert emails.calls[0]["template"] == "email_verification"


# --- magic link ------------------------------------------------------------ #


async def test_magic_link_unknown_is_non_enumerating(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    unknown = await async_client.post(f"{AUTH}/magic-link", json={"email": "ghost@example.com"})
    assert unknown.status_code == 202
    assert emails.calls == []


async def test_magic_link_known_enqueues_one_and_callback_logs_in(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="mag@example.com")
    req = await async_client.post(f"{AUTH}/magic-link", json={"email": "mag@example.com"})
    assert req.status_code == 202
    assert len(emails.calls) == 1
    call = emails.calls[0]
    assert call["template"] == "magic_login"
    assert "/magic-link?token=" in call["context"]["magic_url"]
    raw = _token_from(call, "magic_url")

    cb = await async_client.post(f"{AUTH}/magic-link/callback", json={"token": raw})
    assert cb.status_code == 200, cb.text
    pair = cb.json()
    # The access token authenticates /users/me.
    me = await async_client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {pair['access_token']}"}
    )
    assert me.status_code == 200 and me.json()["email"] == "mag@example.com"
    # The refresh token is a real, rotatable member of the store (spec 07/08).
    rot = await async_client.post(f"{AUTH}/refresh", json={"refresh_token": pair["refresh_token"]})
    assert rot.status_code == 200

    # Replay of the magic token → 400.
    replay = await async_client.post(f"{AUTH}/magic-link/callback", json={"token": raw})
    assert replay.status_code == 400


async def test_magic_link_expired_returns_410(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="magexp@example.com")
    await async_client.post(f"{AUTH}/magic-link", json={"email": "magexp@example.com"})
    raw = _token_from(emails.calls[0], "magic_url")
    await _expire_all(db_session)
    gone = await async_client.post(f"{AUTH}/magic-link/callback", json={"token": raw})
    assert gone.status_code == 410


# --- password reset -------------------------------------------------------- #


async def test_forgot_password_unknown_is_non_enumerating(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    resp = await async_client.post(f"{AUTH}/forgot-password", json={"email": "ghost@example.com"})
    assert resp.status_code == 202
    assert emails.calls == []


async def test_reset_password_revokes_sessions_and_rotates_password(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="reset@example.com")
    # Log in first to mint a refresh token we can prove gets revoked.
    login = await async_client.post(
        f"{AUTH}/login", json={"email": "reset@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    old_refresh = login.json()["refresh_token"]

    req = await async_client.post(f"{AUTH}/forgot-password", json={"email": "reset@example.com"})
    assert req.status_code == 202
    assert len(emails.calls) == 1
    call = emails.calls[0]
    assert call["template"] == "password_reset"
    assert call["to"] == "reset@example.com"
    raw = _token_from(call, "reset_url")

    new_password = "Br4ndNewPass"
    reset = await async_client.post(
        f"{AUTH}/reset-password", json={"token": raw, "new_password": new_password}
    )
    assert reset.status_code == 200, reset.text

    # All pre-existing sessions revoked: the old refresh token can't rotate.
    rot = await async_client.post(f"{AUTH}/refresh", json={"refresh_token": old_refresh})
    assert rot.status_code == 401

    # New password logs in; the old one does not.
    new_login = await async_client.post(
        f"{AUTH}/login", json={"email": "reset@example.com", "password": new_password}
    )
    assert new_login.status_code == 200
    old_login = await async_client.post(
        f"{AUTH}/login", json={"email": "reset@example.com", "password": PASSWORD}
    )
    assert old_login.status_code == 401

    # Email is confirmed by the reset (the link proved inbox ownership).
    user = await db_session.scalar(select(User).where(User.email == "reset@example.com"))
    assert user is not None and user.email_confirmed is True


async def test_reset_password_weak_is_400(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    await _user(db_session, email="weak@example.com")
    await async_client.post(f"{AUTH}/forgot-password", json={"email": "weak@example.com"})
    raw = _token_from(emails.calls[0], "reset_url")
    # Too short / no digit — schema/`new_password` Field min is 8, so use 8 letters
    # (passes schema length) but fails the service's letter+digit rule → 400.
    weak = await async_client.post(
        f"{AUTH}/reset-password", json={"token": raw, "new_password": "onlyletters"}
    )
    assert weak.status_code == 400


# --- rate limiting (spec 52 reuse) ----------------------------------------- #


async def test_magic_link_request_rate_limited(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from inkstave.config import get_settings as _gs

    _gs.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_MAGIC_LINK", "2/3600")
    payload = {"email": "throttle@example.com"}
    assert (await async_client.post(f"{AUTH}/magic-link", json=payload)).status_code == 202
    assert (await async_client.post(f"{AUTH}/magic-link", json=payload)).status_code == 202
    third = await async_client.post(f"{AUTH}/magic-link", json=payload)
    assert third.status_code == 429
    assert third.json()["error"]["type"] == "rate_limited"
    _gs.cache_clear()


# --- login flag (parametrized) --------------------------------------------- #


@pytest.mark.parametrize("require_verified", [True, False])
async def test_login_verified_email_flag(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    require_verified: bool,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("REQUIRE_VERIFIED_EMAIL_TO_LOGIN", "true" if require_verified else "false")
    get_settings.cache_clear()
    await _user(db_session, email="flag@example.com", confirmed=False)
    resp = await async_client.post(
        f"{AUTH}/login", json={"email": "flag@example.com", "password": PASSWORD}
    )
    if require_verified:
        assert resp.status_code == 401
    else:
        assert resp.status_code == 200
    get_settings.cache_clear()
