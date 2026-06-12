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
