"""Auth-subsystem logging & exception visibility (spec 92).

Pure unit tests with in-memory fakes (no DB / Redis / real JWT crypto). They
assert structured log records appear at the right levels and — the overriding
constraint — that no record ever contains a password or a raw token.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from inkstave.services import auth as auth_svc
from inkstave.services import user as user_svc
from inkstave.services.auth import (
    InvalidCredentialsError,
    RefreshError,
    login,
    logout,
    refresh_tokens,
)
from inkstave.services.user import EmailAlreadyExistsError, register_user

PASSWORD = "hunter2-super-secret-pw"
ACCESS_RAW = "ACCESS-TOKEN-RAW-VALUE"
REFRESH_RAW = "REFRESH-TOKEN-RAW-VALUE"
_SUB = uuid4()
_FAMILY = uuid4()


# --- fakes ----------------------------------------------------------------- #


class _ScalarResult:
    def __init__(self, user: Any) -> None:
        self._user = user

    def scalar_one_or_none(self) -> Any:
        return self._user


class FakeAuthSession:
    """Stands in for an AsyncSession for the auth-service paths only."""

    def __init__(self, user: Any = None) -> None:
        self._user = user

    async def execute(self, _stmt: Any) -> _ScalarResult:
        return _ScalarResult(self._user)

    async def get(self, _model: Any, _pk: Any) -> Any:
        return self._user


class FakeHasher:
    def __init__(self, *, ok: bool = True) -> None:
        self._ok = ok

    def hash(self, _plain: str) -> str:
        return "$argon2id$dummy"

    def verify(self, _plain: str, _hashed: str) -> bool:
        return self._ok


class FakeTokenService:
    def create_access_token(self, _user: Any) -> tuple[str, int]:
        return ACCESS_RAW, 900

    def create_refresh_token(self, _user_id: Any, _family_id: Any) -> tuple[str, str]:
        return REFRESH_RAW, "jti-new"

    def decode_token(self, _token: str, _kind: str) -> dict[str, str]:
        return {"jti": "jti-1", "family_id": str(_FAMILY), "sub": str(_SUB)}


class FakeRefreshStore:
    def __init__(
        self, *, record: Any = None, family_revoked: bool = False, user_revoked: bool = False
    ) -> None:
        self._record = record
        self._family_revoked = family_revoked
        self._user_revoked = user_revoked
        self.stored: list[str] = []
        self.revoked_family: str | None = None
        self.rotated_jti: str | None = None

    async def store_refresh(self, *, jti: str, user_id: Any, family_id: Any) -> None:
        self.stored.append(jti)

    async def get_refresh(self, _jti: str) -> Any:
        return self._record

    async def is_family_revoked(self, _family_id: str) -> bool:
        return self._family_revoked

    async def revoke_family(self, family_id: str) -> None:
        self.revoked_family = family_id

    async def is_user_revoked(self, _record: Any) -> bool:
        return self._user_revoked

    async def rotate_refresh(self, jti: str) -> None:
        self.rotated_jti = jti


def _user() -> Any:
    return SimpleNamespace(id=_SUB, hashed_password="$argon2id$dummy", email="u@example.com")


def _login_data() -> Any:
    return SimpleNamespace(email="u@example.com", password=PASSWORD)


def _records(caplog: pytest.LogCaptureFixture, logger: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == logger]


# --- #A1: auth-flow logging ------------------------------------------------ #


async def test_failed_login_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeAuthSession(user=None)
    with caplog.at_level(logging.DEBUG), pytest.raises(InvalidCredentialsError):
        await login(
            session, FakeHasher(ok=False), FakeTokenService(), FakeRefreshStore(), _login_data()
        )
    warnings = [
        r for r in _records(caplog, "inkstave.services.auth") if r.levelno == logging.WARNING
    ]
    assert warnings, "a WARNING should be logged on failed login"
    assert PASSWORD not in caplog.text and "u@example.com" not in caplog.text


async def test_successful_login_logs_info_without_secrets(caplog: pytest.LogCaptureFixture) -> None:
    session = FakeAuthSession(user=_user())
    with caplog.at_level(logging.INFO):
        pair = await login(
            session, FakeHasher(ok=True), FakeTokenService(), FakeRefreshStore(), _login_data()
        )
    assert pair.access_token == ACCESS_RAW
    infos = [r for r in _records(caplog, "inkstave.services.auth") if r.levelno == logging.INFO]
    assert any("login ok" in r.getMessage() for r in infos)
    assert PASSWORD not in caplog.text
    assert ACCESS_RAW not in caplog.text and REFRESH_RAW not in caplog.text


async def test_refresh_reuse_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    rotated = SimpleNamespace(user_id=str(_SUB), rotated=True)
    store = FakeRefreshStore(record=rotated)
    with caplog.at_level(logging.WARNING), pytest.raises(RefreshError):
        await refresh_tokens(FakeAuthSession(), FakeTokenService(), store, REFRESH_RAW)
    assert store.revoked_family == str(_FAMILY)  # family was revoked (behaviour unchanged)
    warnings = [
        r for r in _records(caplog, "inkstave.services.auth") if r.levelno == logging.WARNING
    ]
    assert any("reuse detected" in r.getMessage() for r in warnings)
    assert REFRESH_RAW not in caplog.text


async def test_successful_refresh_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    fresh = SimpleNamespace(user_id=str(_SUB), rotated=False)
    store = FakeRefreshStore(record=fresh)
    with caplog.at_level(logging.INFO):
        await refresh_tokens(FakeAuthSession(user=_user()), FakeTokenService(), store, REFRESH_RAW)
    assert store.rotated_jti == "jti-1"
    infos = [r for r in _records(caplog, "inkstave.services.auth") if r.levelno == logging.INFO]
    assert any("refresh rotated" in r.getMessage() for r in infos)
    assert REFRESH_RAW not in caplog.text and ACCESS_RAW not in caplog.text


async def test_logout_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    store = FakeRefreshStore()
    with caplog.at_level(logging.INFO):
        await logout(FakeTokenService(), store, REFRESH_RAW)
    assert store.revoked_family == str(_FAMILY)
    infos = [r for r in _records(caplog, "inkstave.services.auth") if r.levelno == logging.INFO]
    assert any("logout" in r.getMessage() for r in infos)
    assert REFRESH_RAW not in caplog.text


# --- #A2: registration logging --------------------------------------------- #


class FakeRegResult:
    def __init__(self, exists: bool) -> None:
        self._exists = exists

    def first(self) -> Any:
        return object() if self._exists else None


class FakeUserSession:
    def __init__(self, *, exists: bool = False, flush_raises: bool = False) -> None:
        self._exists = exists
        self._flush_raises = flush_raises

    async def execute(self, _stmt: Any) -> FakeRegResult:
        return FakeRegResult(self._exists)

    def add(self, _obj: Any) -> None:
        return None

    async def flush(self) -> None:
        if self._flush_raises:
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()


def _reg_data() -> Any:
    return SimpleNamespace(email="New@Example.com", password=PASSWORD, display_name="New User")


async def test_register_success_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        await register_user(FakeUserSession(), FakeHasher(), _reg_data())
    infos = [r for r in _records(caplog, "inkstave.services.user") if r.levelno == logging.INFO]
    assert any("user registered" in r.getMessage() for r in infos)
    assert PASSWORD not in caplog.text and "new@example.com" not in caplog.text


async def test_register_duplicate_precheck_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), pytest.raises(EmailAlreadyExistsError):
        await register_user(FakeUserSession(exists=True), FakeHasher(), _reg_data())
    warnings = [
        r for r in _records(caplog, "inkstave.services.user") if r.levelno == logging.WARNING
    ]
    assert warnings and PASSWORD not in caplog.text


async def test_register_integrity_race_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), pytest.raises(EmailAlreadyExistsError):
        await register_user(FakeUserSession(flush_raises=True), FakeHasher(), _reg_data())
    warnings = [
        r for r in _records(caplog, "inkstave.services.user") if r.levelno == logging.WARNING
    ]
    assert warnings and PASSWORD not in caplog.text


# --- #A4: rate-limit body-parse fallback ----------------------------------- #


async def test_rate_limit_body_parse_fallback_logs_and_uses_ip(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from inkstave.auth.rate_limit import _identity
    from inkstave.config import get_settings

    class BadRequest:
        client = SimpleNamespace(host="203.0.113.7")
        headers: dict[str, str] = {}

        async def json(self) -> Any:
            raise ValueError("not json")

    settings = get_settings().model_copy(update={"trust_proxy_headers": False})
    with caplog.at_level(logging.DEBUG, logger="inkstave.ratelimit"):
        identity = await _identity(BadRequest(), "login", settings)
    assert identity == "203.0.113.7"  # IP-only fallback, behaviour unchanged
    assert any(r.name == "inkstave.ratelimit" for r in caplog.records)


# --- shared module-logger sanity ------------------------------------------- #


def test_modules_have_loggers() -> None:
    assert auth_svc.logger.name == "inkstave.services.auth"
    assert user_svc.logger.name == "inkstave.services.user"
