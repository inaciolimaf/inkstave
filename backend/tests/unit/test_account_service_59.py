"""Isolated unit tests for the spec-59 account service (spec 59 §8; spec 68 #247).

Repositories, the session, hasher and refresh store are all mocked so no DB is
touched. These assert the security invariants that the integration suite only
exercises end-to-end: current-password re-auth, re-hashing, single-session
revocation, and that confirm_email_change hashes the token (never compares raw).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from inkstave.errors import GoneError, UnauthorizedError
from inkstave.services import account
from inkstave.services.sharing import hash_token


class _FakeHasher:
    """Verifies against a known plaintext; hashes by prefixing so we can assert
    a *new* hash was produced without running argon2."""

    def __init__(self, valid_plain: str) -> None:
        self._valid = valid_plain

    def verify(self, plain: str, _hashed: str) -> bool:
        return plain == self._valid

    def hash(self, plain: str) -> str:
        return f"hashed::{plain}"


class _FakeSession:
    def __init__(self, user: Any = None) -> None:
        self._user = user
        self.flushed = False

    async def flush(self) -> None:
        self.flushed = True

    async def scalar(self, _stmt: Any) -> Any:
        return self._user


class _FakeRefreshStore:
    def __init__(self) -> None:
        self.revoked: list[Any] = []

    async def revoke_user(self, user_id: Any) -> None:
        self.revoked.append(user_id)


def _user(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": "user-1",
        "email": "ada@example.com",
        "hashed_password": "old-hash",
        "pending_email": None,
        "email_change_token_hash": None,
        "email_change_expires_at": None,
        "email_confirmed": False,
    }
    base.update(over)
    return SimpleNamespace(**base)


# --- change_password --------------------------------------------------------- #


async def test_change_password_rehashes_and_revokes_sessions() -> None:
    user = _user()
    hasher = _FakeHasher(valid_plain="correct-old")
    session = _FakeSession()
    store = _FakeRefreshStore()

    await account.change_password(
        session,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        hasher,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        current_password="correct-old",
        new_password="brandnew123",
    )

    assert user.hashed_password == "hashed::brandnew123"  # re-hashed, not the old value
    assert session.flushed is True
    assert store.revoked == ["user-1"]  # all other sessions signed out


async def test_change_password_rejects_wrong_current_password() -> None:
    user = _user()
    hasher = _FakeHasher(valid_plain="correct-old")
    session = _FakeSession()
    store = _FakeRefreshStore()

    with pytest.raises(UnauthorizedError):
        await account.change_password(
            session,  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            hasher,  # type: ignore[arg-type]
            user,  # type: ignore[arg-type]
            current_password="WRONG",
            new_password="brandnew123",
        )

    assert user.hashed_password == "old-hash"  # unchanged
    assert store.revoked == []  # no session revocation on a failed re-auth


# --- confirm_email_change ---------------------------------------------------- #


async def test_confirm_email_change_matches_hashed_token_never_raw() -> None:
    raw_token = "raw-confirm-token"
    user = _user(
        pending_email="new@example.com",
        # The stored value is the *hash* of the raw token — never the raw token.
        email_change_token_hash=hash_token(raw_token),
        email_change_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session = _FakeSession(user=user)

    result = await account.confirm_email_change(session, token=raw_token)  # type: ignore[arg-type]

    assert result.email == "new@example.com"
    assert result.email_confirmed is True
    # Single-use: the pending fields are cleared after a successful confirm.
    assert result.pending_email is None
    assert result.email_change_token_hash is None
    assert result.email_change_expires_at is None
    assert user.email_change_token_hash != raw_token  # raw token was never stored


async def test_confirm_email_change_rejects_expired_token() -> None:
    raw_token = "raw-confirm-token"
    user = _user(
        pending_email="new@example.com",
        email_change_token_hash=hash_token(raw_token),
        email_change_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    session = _FakeSession(user=user)

    with pytest.raises(GoneError):
        await account.confirm_email_change(session, token=raw_token)  # type: ignore[arg-type]

    assert user.email == "ada@example.com"  # email not swapped on an expired token
