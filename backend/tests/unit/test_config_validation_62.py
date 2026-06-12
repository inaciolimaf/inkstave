"""Spec 62: the friendly required-runtime config validator.

Pure string-in → list-out checks; no real DB/Redis, no server boot.
"""

from __future__ import annotations

from inkstave.bootstrap.config_check import (
    format_config_problems,
    validate_required_runtime,
)

_VALID = {
    "JWT_SECRET": "a-strong-secret-value-of-sufficient-length-0123456789",
    "DATABASE_URL": "postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave",
    "REDIS_URL": "redis://localhost:6379/0",
}


def _env(**over: str | None) -> dict[str, str]:
    env = dict(_VALID)
    for key, value in over.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def test_valid_config_has_no_problems() -> None:  # AC5
    assert validate_required_runtime(_env()) == []


def test_missing_jwt_secret_is_named() -> None:  # AC1
    problems = validate_required_runtime(_env(JWT_SECRET=None))
    assert any(p.startswith("JWT_SECRET") for p in problems)
    rendered = format_config_problems(problems)
    assert "Traceback" not in rendered


def test_empty_jwt_secret_is_named() -> None:  # AC1
    problems = validate_required_runtime(_env(JWT_SECRET="   "))
    assert any(p.startswith("JWT_SECRET") for p in problems)


def test_missing_database_url_is_named() -> None:  # AC2
    problems = validate_required_runtime(_env(DATABASE_URL=None))
    assert any(p.startswith("DATABASE_URL") for p in problems)


def test_malformed_database_url_is_named() -> None:  # AC2
    problems = validate_required_runtime(_env(DATABASE_URL="mysql://x/y"))
    assert any(p.startswith("DATABASE_URL") for p in problems)


def test_missing_redis_url_is_named() -> None:  # AC3
    problems = validate_required_runtime(_env(REDIS_URL=None))
    assert any(p.startswith("REDIS_URL") for p in problems)


def test_malformed_redis_url_is_named() -> None:  # AC3
    problems = validate_required_runtime(_env(REDIS_URL="http://localhost:6379"))
    assert any(p.startswith("REDIS_URL") for p in problems)


def test_all_missing_are_listed() -> None:  # AC4
    problems = validate_required_runtime(_env(JWT_SECRET=None, DATABASE_URL=None, REDIS_URL=None))
    assert len(problems) == 3
    starts = {p.split(":", 1)[0] for p in problems}
    assert starts == {"JWT_SECRET", "DATABASE_URL", "REDIS_URL"}


def test_format_has_summary_and_no_traceback() -> None:  # AC1/AC4 message shape
    problems = validate_required_runtime(_env(JWT_SECRET=None, REDIS_URL=None))
    rendered = format_config_problems(problems)
    lines = rendered.splitlines()
    assert lines[0] == "Configuration error: 2 problem(s)"
    assert all(line.startswith("  - ") for line in lines[1:])
    assert "Traceback" not in rendered
