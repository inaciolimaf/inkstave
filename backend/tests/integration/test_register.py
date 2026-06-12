"""Integration tests for POST /api/v1/auth/register."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import build_password_hasher
from inkstave.config import get_settings
from inkstave.db.models.user import User
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

REGISTER_URL = "/api/v1/auth/register"


async def _user_count(session: AsyncSession, email: str | None = None) -> int:
    stmt = select(func.count()).select_from(User)
    if email is not None:
        stmt = stmt.where(User.email == email)
    return int((await session.execute(stmt)).scalar_one())


async def test_register_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    payload = {"email": "Alice@Ex.com", "password": "secret123", "display_name": "  Alice  "}
    resp = await async_client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 201

    body = resp.json()
    assert body["email"] == "alice@ex.com"  # normalised
    assert body["display_name"] == "Alice"  # trimmed
    assert body["is_admin"] is False
    assert body["email_confirmed"] is False
    assert "id" in body and "created_at" in body
    assert "hashed_password" not in body
    assert "password" not in body

    # The stored hash is argon2id, not the plaintext, and verifies.
    user = (await db_session.execute(select(User).where(User.email == "alice@ex.com"))).scalar_one()
    assert user.hashed_password.startswith("$argon2id$")
    assert user.hashed_password != "secret123"
    hasher = build_password_hasher(get_settings())
    assert hasher.verify("secret123", user.hashed_password) is True


async def test_register_duplicate_is_conflict(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    first = {"email": "bob@ex.com", "password": "secret123", "display_name": "Bob"}
    assert (await async_client.post(REGISTER_URL, json=first)).status_code == 201

    # Different case -> same account.
    second = {"email": "BOB@EX.com", "password": "another9", "display_name": "Bobby"}
    resp = await async_client.post(REGISTER_URL, json=second)
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["type"] == "conflict"
    assert "already exists" in body["error"]["message"]
    assert await _user_count(db_session, "bob@ex.com") == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "secret123", "display_name": "X"},
        {"email": "weak@ex.com", "password": "short1", "display_name": "X"},  # too short
        {"email": "weak@ex.com", "password": "abcdefgh", "display_name": "X"},  # no digit
        {"email": "weak@ex.com", "password": "12345678", "display_name": "X"},  # no letter
        {"email": "weak@ex.com", "password": "a1" + "x" * 80, "display_name": "X"},  # >72 chars
        {"email": "weak@ex.com", "password": "weak1234", "display_name": "X"},  # local-part in pwd
        {"email": "weak@ex.com", "password": "secret123", "display_name": "   "},  # empty name
    ],
)
async def test_register_validation_errors(
    async_client: AsyncClient, db_session: AsyncSession, payload: dict[str, str]
) -> None:
    resp = await async_client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"
    assert await _user_count(db_session) == 0


async def test_register_integrity_race_yields_conflict(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Pre-existing row, committed so it survives the request's savepoint rollback.
    await UserFactory.create(db_session, email="race@ex.com", display_name="Race")
    await db_session.commit()

    # Force the pre-check to miss so the INSERT races into the unique constraint.
    import inkstave.services.user as user_service

    async def _never_exists(*_a: Any, **_k: Any) -> bool:
        return False

    monkeypatch.setattr(user_service, "email_exists", _never_exists)

    payload = {"email": "race@ex.com", "password": "secret123", "display_name": "Racer"}
    resp = await async_client.post(REGISTER_URL, json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "conflict"
    assert await _user_count(db_session, "race@ex.com") == 1
