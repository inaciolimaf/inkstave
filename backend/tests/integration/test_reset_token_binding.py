"""A password-reset link dies with the state it was issued for (defect: auth audit).

A reset link is bound to the e-mail address it was sent to and to the password it
was issued under; an e-mail change, a password change or a deactivation must make
it unusable, even before its TTL runs out.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.infra.deps import get_email_enqueuer
from inkstave.modules.auth.accounts.users import normalise_email
from inkstave.modules.auth.credentials.password import build_password_hasher
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"
USERS = "/api/v1/users"
PASSWORD = "Sup3rPass"
NEW_PASSWORD = "Br4ndNewPass"


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


async def _user(db: AsyncSession, email: str = "reset@example.com") -> User:
    hasher = build_password_hasher(get_settings())
    user = User(
        email=normalise_email(email),
        hashed_password=hasher.hash(PASSWORD),
        display_name="Reset",
        email_confirmed=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _issue_reset_link(client: AsyncClient, emails: FakeEmailEnqueuer, email: str) -> str:
    assert (await client.post(f"{AUTH}/forgot-password", json={"email": email})).status_code == 202
    return emails.calls[-1]["context"]["reset_url"].split("token=", 1)[1]


async def _reset(client: AsyncClient, token: str) -> int:
    body = {"token": token, "new_password": NEW_PASSWORD}
    return (await client.post(f"{AUTH}/reset-password", json=body)).status_code


async def test_reset_link_is_refused_after_an_email_change(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    user = await _user(db_session)
    token = await _issue_reset_link(async_client, emails, "reset@example.com")

    # The address changes (staged, then confirmed through its own link).
    started = await async_client.post(
        f"{USERS}/me/change-email",
        json={"new_email": "moved@example.com", "current_password": PASSWORD},
        headers=_headers(user),
    )
    assert started.status_code == 202
    confirm_token = emails.calls[-1]["context"]["confirm_url"].split("token=", 1)[1]
    confirmed = await async_client.post(f"{USERS}/confirm-email-change", json={"token": confirm_token})
    assert confirmed.status_code == 200

    assert await _reset(async_client, token) == 400


async def test_reset_link_is_refused_after_an_email_change_and_back(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    # Changing away and back to the same address must not revive an old link.
    user = await _user(db_session)
    token = await _issue_reset_link(async_client, emails, "reset@example.com")
    for new_address in ("moved@example.com", "reset@example.com"):
        await async_client.post(
            f"{USERS}/me/change-email",
            json={"new_email": new_address, "current_password": PASSWORD},
            headers=_headers(user),
        )
        confirm_token = emails.calls[-1]["context"]["confirm_url"].split("token=", 1)[1]
        assert (
            await async_client.post(f"{USERS}/confirm-email-change", json={"token": confirm_token})
        ).status_code == 200

    assert await _reset(async_client, token) == 400


async def test_reset_link_is_refused_after_a_password_change(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    user = await _user(db_session)
    token = await _issue_reset_link(async_client, emails, "reset@example.com")

    changed = await async_client.post(
        f"{USERS}/me/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=_headers(user),
    )
    assert changed.status_code == 200

    assert await _reset(async_client, token) == 400


async def test_deactivated_user_cannot_complete_a_reset(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    user = await _user(db_session)
    token = await _issue_reset_link(async_client, emails, "reset@example.com")
    user.is_active = False
    await db_session.commit()

    assert await _reset(async_client, token) == 400
    await db_session.refresh(user)
    assert build_password_hasher(get_settings()).verify(PASSWORD, user.hashed_password)


async def test_reset_link_still_works_for_the_untouched_account(
    async_client: AsyncClient, db_session: AsyncSession, emails: FakeEmailEnqueuer
) -> None:
    # Guard against over-blocking: a plain reset keeps working.
    await _user(db_session)
    token = await _issue_reset_link(async_client, emails, "reset@example.com")

    assert await _reset(async_client, token) == 200
