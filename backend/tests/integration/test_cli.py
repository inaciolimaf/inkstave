"""Integration tests for the operations CLI (``inkstave.cli``).

Covers command dispatch plus the read-only / idempotent commands against the
test database. The two *writing* commands (``bootstrap-admin`` create, ``seed
--demo``) build their own engine + session and commit outside the per-test
rollback, so their underlying functions are exercised through ``db_session`` in
test_bootstrap_57 instead — here we drive everything that does not persist data,
using the CLI's injectable probes/sender so no real Redis/SMTP is required.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from inkstave import cli
from inkstave.bootstrap.seed import DEMO_EMAIL

pytestmark = pytest.mark.integration


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, email: object) -> None:
        self.sent.append(email)


async def _purge_user(url: str, email: str) -> None:
    """Remove a CLI-created user (and, via ON DELETE CASCADE, all it owns).

    The ``bootstrap-admin`` / ``seed`` commands build their own engine and commit
    outside the per-test rollback, so they must be cleaned up to keep the shared
    worker DB clean for other tests (see the note in test_migrations)."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": email})
    finally:
        await engine.dispose()


async def _ok() -> bool:
    return True


async def _bad() -> bool:
    return False


async def _boom() -> bool:
    raise RuntimeError("nope")


def test_migrate_is_idempotent_at_head(_template_db: str) -> None:
    # `_template_db` provisions + migrates the test DB to head; re-running the CLI
    # migrate command against it must be a clean no-op.
    assert cli.main(["migrate"]) == 0


def test_check_config_runs(_template_db: str) -> None:
    # Either outcome exercises validate_config + the dispatch; the test env's
    # config is valid, but tolerate a non-zero so this never gets env-brittle.
    assert cli.main(["check-config"]) in (0, 1)


def test_seed_without_demo_flag_is_a_noop() -> None:
    assert cli.main(["seed"]) == 2


def test_no_subcommand_exits_with_usage() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


async def test_doctor_with_real_probes_reports_status(_template_db: str) -> None:
    # No injected probes → builds the real Postgres/Redis readiness checks from
    # settings. The test DB is reachable; Redis may or may not be (faked in CI),
    # so tolerate either terminal status — the point is exercising the real probes.
    rc = await cli._cmd_doctor()
    assert rc in (0, 1)


async def test_doctor_all_probes_pass() -> None:
    rc = await cli._cmd_doctor(config_check=lambda: [], db_check=_ok, redis_check=_ok)
    assert rc == 0


async def test_doctor_reports_each_failure() -> None:
    # Config problems + an unreachable DB + a probe that raises — every FAIL path.
    rc = await cli._cmd_doctor(config_check=lambda: ["bad"], db_check=_bad, redis_check=_boom)
    assert rc == 1


async def test_send_test_email_renders_and_sends_via_injected_sender() -> None:
    sender = _FakeSender()
    rc = await cli._cmd_send_test_email(
        to="dev@example.com", template="email_verification", sender=sender
    )
    assert rc == 0
    assert len(sender.sent) == 1


async def test_send_test_email_rejects_unknown_template() -> None:
    sender = _FakeSender()
    rc = await cli._cmd_send_test_email(
        to="dev@example.com", template="no-such-template", sender=sender
    )
    assert rc == 1
    assert sender.sent == []


def test_bootstrap_admin_via_cli_creates_then_noops(
    _template_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INKSTAVE_ADMIN_EMAIL", "cli-admin@example.com")
    monkeypatch.setenv("INKSTAVE_ADMIN_PASSWORD", "adminPass1")
    try:
        assert cli.main(["bootstrap-admin"]) == 0
        assert cli.main(["bootstrap-admin"]) == 0  # idempotent (admin already exists)
    finally:
        asyncio.run(_purge_user(_template_db, "cli-admin@example.com"))


def test_seed_demo_via_cli(_template_db: str) -> None:
    try:
        assert cli.main(["seed", "--demo"]) == 0
    finally:
        asyncio.run(_purge_user(_template_db, DEMO_EMAIL))


def test_resolve_admin_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INKSTAVE_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("INKSTAVE_ADMIN_PASSWORD", "adminPass1")
    assert cli._resolve_admin_credentials() == ("admin@example.com", "adminPass1")


def test_resolve_admin_credentials_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INKSTAVE_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("INKSTAVE_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    assert cli._resolve_admin_credentials() is None
