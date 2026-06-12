"""Spec-57 unit tests: fail-fast config guards, the migration runner, the seed
guard, and the check-config CLI exit codes. No DB, no network — pure logic.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from inkstave.bootstrap import migrate
from inkstave.config import Settings

_STRONG_SECRET = "x" * 40


def _prod(**over: Any) -> dict[str, Any]:
    base = dict(
        environment="prod",
        jwt_secret=_STRONG_SECRET,
        cors_origins=["https://app.example.com"],
        database_url="postgresql+asyncpg://u:p@db:5432/inkstave",
        # An explicit, non-default REDIS_URL: production rejects the localhost
        # default, so the helper must supply a real one to stay hermetic regardless
        # of the ambient environment.
        redis_url="redis://cache:6379/0",
    )
    base.update(over)
    return base


# --- Spec 57 §5.6: fail-fast production guards -------------------------------- #


def test_production_requires_strong_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None, **_prod(jwt_secret="secret"))  # type: ignore[arg-type]


def test_production_requires_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(_env_file=None, **_prod(database_url=None))  # type: ignore[arg-type]


def test_production_requires_cors_origins() -> None:
    with pytest.raises(ValueError, match="CORS"):
        Settings(_env_file=None, **_prod(cors_origins=[]))  # type: ignore[arg-type]


def test_valid_production_settings_construct() -> None:
    settings = Settings(_env_file=None, **_prod())  # type: ignore[arg-type]
    assert settings.environment == "prod" and not settings.migrate_on_start


def test_dev_settings_use_lenient_defaults() -> None:
    # No required secrets outside production — the app must construct cleanly
    # (the active env is "test" here, set by conftest; the point is no guard fires).
    settings = Settings(_env_file=None, environment="dev", jwt_secret="dev")  # type: ignore[arg-type]
    assert settings.environment == "dev" and settings.cors_origins


# --- Spec 57 §5.3: migration runner ------------------------------------------ #


class _FakeConn:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def exec_driver_sql(self, sql: str, params: dict[str, Any] | None = None) -> None:
        if "pg_advisory_lock" in sql:
            self._calls.append("lock")
        elif "pg_advisory_unlock" in sql:
            self._calls.append("unlock")


class _FakeEngine:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def connect(self) -> _FakeConn:
        return _FakeConn(self._calls)

    def dispose(self) -> None:
        self._calls.append("dispose")


def test_run_upgrade_locks_then_upgrades_then_unlocks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(migrate, "create_engine", lambda *a, **k: _FakeEngine(calls))
    monkeypatch.setattr(migrate.command, "upgrade", lambda cfg, rev: calls.append(f"upgrade:{rev}"))

    migrate.run_upgrade(
        Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@db/x")  # type: ignore[arg-type]
    )
    # The advisory lock wraps the upgrade, then is released before dispose.
    assert calls == ["lock", "upgrade:head", "unlock", "dispose"]


class _FakeResult:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def scalar(self) -> str | None:
        return self._value


class _FakeAsyncConn:
    def __init__(self, value: str | None) -> None:
        self._value = value

    async def __aenter__(self) -> _FakeAsyncConn:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def exec_driver_sql(self, sql: str) -> _FakeResult:
        return _FakeResult(self._value)


class _FakeAsyncEngine:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def connect(self) -> _FakeAsyncConn:
        return _FakeAsyncConn(self._value)


async def test_is_database_at_head_compares_to_script_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(migrate, "script_head", lambda ini=None: "rev_head")
    assert await migrate.is_database_at_head(_FakeAsyncEngine("rev_head"))  # type: ignore[arg-type]
    assert not await migrate.is_database_at_head(_FakeAsyncEngine("rev_old"))  # type: ignore[arg-type]
    assert not await migrate.is_database_at_head(_FakeAsyncEngine(None))  # type: ignore[arg-type]


# --- Spec 57 §8 / AC5: strict mode refuses to start when DB is behind head --- #


async def test_strict_mode_refuses_to_start_when_db_behind_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MIGRATE_ON_START=false + DB not at head -> app refuses to start (AC5)."""
    from inkstave import app as app_module

    # DB is behind head; strict mode (migrate_on_start=False) must abort startup.
    async def _not_at_head(_engine: Any) -> bool:
        return False

    monkeypatch.setattr(app_module, "is_database_at_head", _not_at_head, raising=False)
    monkeypatch.setattr(
        "inkstave.bootstrap.migrate.is_database_at_head", _not_at_head, raising=False
    )
    settings = Settings(_env_file=None, migrate_on_start=False)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="not at the latest migration"):
        await app_module._ensure_migrations(object(), settings)


# --- Spec 57 §5.5: seed refuses in production -------------------------------- #


async def test_seed_demo_refuses_in_production() -> None:
    from inkstave.bootstrap.seed import seed_demo

    settings = Settings(_env_file=None, **_prod())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="production"):
        # The prod guard fires before any DB access, so a dummy session is fine.
        await seed_demo(MagicMock(), MagicMock(), settings=settings, force=False)


# --- Spec 57 §5.6: check-config CLI exit codes ------------------------------- #


def test_check_config_cli_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave import cli

    monkeypatch.setattr(cli, "validate_config", lambda: [])
    assert cli._cmd_check_config() == 0

    monkeypatch.setattr(cli, "validate_config", lambda: ["JWT_SECRET missing"])
    assert cli._cmd_check_config() == 1
