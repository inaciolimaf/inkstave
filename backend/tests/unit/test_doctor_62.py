"""Spec 62 AC7/AC8: the `doctor` CLI with injected dependency probes.

No real Postgres/Redis — probes are injected callables. Asserts exit codes and
that failures print a friendly line rather than a traceback.
"""

from __future__ import annotations

import pytest

from inkstave.cli import _cmd_doctor


async def _ok() -> bool:
    return True


async def _fail() -> bool:
    return False


async def _raises() -> bool:
    raise ConnectionError("connection refused")


async def test_all_pass_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:  # AC8
    rc = await _cmd_doctor(config_check=lambda: [], db_check=_ok, redis_check=_ok)
    assert rc == 0
    out = capsys.readouterr().out
    assert "config: PASS" in out
    assert "postgres: PASS" in out
    assert "redis: PASS" in out


async def test_failing_postgres_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:  # AC7
    rc = await _cmd_doctor(config_check=lambda: [], db_check=_fail, redis_check=_ok)
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "postgres: FAIL" in combined
    assert "Traceback" not in combined


async def test_raising_probe_is_friendly(capsys: pytest.CaptureFixture[str]) -> None:  # AC7
    rc = await _cmd_doctor(config_check=lambda: [], db_check=_raises, redis_check=_ok)
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "postgres: FAIL" in combined
    assert "connection refused" in combined
    assert "Traceback" not in combined


async def test_invalid_config_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:  # AC7
    rc = await _cmd_doctor(
        config_check=lambda: ["JWT_SECRET: must be set"],
        db_check=_ok,
        redis_check=_ok,
    )
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "config: FAIL" in combined
    assert "JWT_SECRET" in combined
    assert "Traceback" not in combined


async def test_doctor_masks_passwords_in_the_urls_it_prints(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:  # auth audit: no secret on the terminal
    from inkstave.core.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://inkstave:s3cr3t-pass@db.internal:5432/inkstave")
    monkeypatch.setenv("REDIS_URL", "redis://:r3dis-pass@cache.internal:6379/0")
    try:
        await _cmd_doctor(config_check=lambda: [], db_check=_fail, redis_check=_fail)
    finally:
        get_settings.cache_clear()
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "s3cr3t-pass" not in combined
    assert "r3dis-pass" not in combined
    assert "inkstave:***@db.internal:5432/inkstave" in combined
    assert "redis://:***@cache.internal:6379/0" in combined


def test_redact_url_keeps_the_host_and_hides_the_password() -> None:
    from inkstave.modules.admin.provisioning.config_check import redact_url

    assert redact_url("postgresql://u:p%40ss@h:5432/db") == "postgresql://u:***@h:5432/db"
    assert redact_url("redis://h:6379/0") == "redis://h:6379/0"
    assert redact_url("redis://:tok@h/0") == "redis://:***@h/0"
