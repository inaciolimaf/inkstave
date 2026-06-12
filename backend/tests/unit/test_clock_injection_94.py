"""Deterministic time-boundary tests via the injectable Clock seam (spec 94).

No real sleeps: a FrozenClock drives token expiry, the refresh-rotation cutoff,
and the email-change-token expiry across their boundaries. Also pins that the
default (no-clock) path is unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import jwt
import pytest

from inkstave.auth.refresh_store import build_refresh_store
from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.errors import GoneError
from inkstave.services.account import confirm_email_change, start_email_change
from inkstave.time import SYSTEM_CLOCK, Clock, SystemClock
from tests.unit._clock import FrozenClock

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# --- the abstraction itself ------------------------------------------------ #


def test_system_clock_is_utc_aware_and_default() -> None:
    assert isinstance(SYSTEM_CLOCK, SystemClock)
    now = SYSTEM_CLOCK.now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)
    assert isinstance(SYSTEM_CLOCK, Clock)  # runtime_checkable protocol


def test_frozen_clock_is_a_clock_and_advances() -> None:
    clock = FrozenClock(BASE)
    assert isinstance(clock, Clock)
    assert clock.now() == BASE
    clock.advance(seconds=30)
    assert clock.now() == BASE + timedelta(seconds=30)


# --- #5.2 token expiry boundary -------------------------------------------- #


def _unverified_claims(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def test_access_token_exp_derives_from_injected_clock() -> None:
    settings = get_settings()
    svc = build_token_service(settings)
    user = SimpleNamespace(id=uuid4(), is_admin=False)
    clock = FrozenClock(BASE)

    token, expires_in = svc.create_access_token(user, clock=clock)
    claims = _unverified_claims(token)
    ttl = settings.access_token_ttl_seconds
    assert expires_in == ttl
    assert claims["iat"] == int(BASE.timestamp())
    assert claims["exp"] == int(BASE.timestamp()) + ttl

    exp_dt = datetime.fromtimestamp(claims["exp"], tz=UTC)
    # Deterministic boundary, no real sleep: not expired just before exp; expired at/after.
    clock.set(BASE + timedelta(seconds=ttl - 1))
    assert clock.now() < exp_dt
    clock.set(BASE + timedelta(seconds=ttl))
    assert clock.now() >= exp_dt
    clock.advance(seconds=1)
    assert clock.now() > exp_dt


def test_token_default_clock_lifetime_unchanged() -> None:
    settings = get_settings()
    svc = build_token_service(settings)
    user = SimpleNamespace(id=uuid4(), is_admin=False)

    access, _ = svc.create_access_token(user)  # no clock -> system clock
    a = _unverified_claims(access)
    assert a["exp"] - a["iat"] == settings.access_token_ttl_seconds

    refresh, _ = svc.create_refresh_token(uuid4(), uuid4())
    r = _unverified_claims(refresh)
    assert r["exp"] - r["iat"] == settings.refresh_token_ttl_seconds


# --- #5.3 refresh rotation / revocation cutoff ----------------------------- #


async def test_refresh_revocation_cutoff_uses_injected_clock(redis: Any) -> None:
    store = build_refresh_store(redis, get_settings())
    uid, fam = uuid4(), uuid4()

    await store.store_refresh(jti="jti-old", user_id=uid, family_id=fam, clock=FrozenClock(BASE))
    rec_old = await store.get_refresh("jti-old")
    assert rec_old is not None and rec_old.created_at == BASE.isoformat()

    # Cutoff strictly after the old token -> the old token is revoked.
    await store.revoke_user(uid, clock=FrozenClock(BASE + timedelta(seconds=10)))
    assert await store.is_user_revoked(rec_old) is True

    # A token minted after the cutoff survives (deterministic boundary).
    await store.store_refresh(
        jti="jti-new", user_id=uid, family_id=fam, clock=FrozenClock(BASE + timedelta(seconds=20))
    )
    rec_new = await store.get_refresh("jti-new")
    assert rec_new is not None and await store.is_user_revoked(rec_new) is False


# --- #5.4 email-change token expiry ---------------------------------------- #


class _FirstResult:
    def __init__(self, found: bool) -> None:
        self._found = found

    def first(self) -> Any:
        return object() if self._found else None


class FakeEmailSession:
    def __init__(self, *, exists: bool = False, user: Any = None) -> None:
        self._exists = exists
        self._user = user

    async def execute(self, _stmt: Any) -> _FirstResult:
        return _FirstResult(self._exists)

    async def scalar(self, _stmt: Any) -> Any:
        return self._user

    async def flush(self) -> None:
        return None


class FakeHasher:
    def verify(self, _plain: str, _hashed: str) -> bool:
        return True


async def test_start_email_change_expiry_uses_injected_clock() -> None:
    settings = get_settings()
    user = SimpleNamespace(
        email="old@example.com",
        hashed_password="$argon2id$dummy",
        pending_email=None,
        email_change_token_hash=None,
        email_change_expires_at=None,
    )
    await start_email_change(
        FakeEmailSession(exists=False),
        FakeHasher(),
        user,
        new_email="new@example.com",
        current_password="pw",
        settings=settings,
        clock=FrozenClock(BASE),
    )
    assert user.email_change_expires_at == BASE + timedelta(seconds=settings.email_change_token_ttl)


def _pending_user() -> Any:
    return SimpleNamespace(
        email="old@example.com",
        email_confirmed=False,
        pending_email="new@example.com",
        email_change_token_hash="hash",
        email_change_expires_at=BASE + timedelta(seconds=100),
    )


async def test_confirm_email_change_succeeds_just_before_expiry() -> None:
    user = _pending_user()
    session = FakeEmailSession(user=user)
    result = await confirm_email_change(
        session, token="raw", clock=FrozenClock(BASE + timedelta(seconds=99))
    )
    assert result.email == "new@example.com" and result.email_confirmed is True


async def test_confirm_email_change_fails_after_expiry() -> None:
    user = _pending_user()
    session = FakeEmailSession(user=user)
    with pytest.raises(GoneError):
        await confirm_email_change(
            session, token="raw", clock=FrozenClock(BASE + timedelta(seconds=101))
        )
