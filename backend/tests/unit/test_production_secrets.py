"""Production refuses to boot on secrets anyone can read or guess."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from inkstave.core.config.settings import EXAMPLE_JWT_SECRET, Settings

STRONG = "a-strong-secret-value-of-sufficient-length-0123456789"
OTHER_STRONG = "another-strong-secret-value-of-sufficient-length-987"
ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def _prod(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "prod",
        "jwt_secret": STRONG,
        "database_url": "postgresql+asyncpg://u:p@db/inkstave",
        "redis_url": "redis://redis:6379/0",
    }
    return Settings(_env_file=None, **{**values, **overrides})  # type: ignore[arg-type,call-arg]


def test_example_constant_matches_env_example() -> None:
    assert f"JWT_SECRET={EXAMPLE_JWT_SECRET}\n" in ENV_EXAMPLE.read_text()


def test_strong_secrets_boot() -> None:
    assert _prod(jwt_secret_previous=[OTHER_STRONG]).jwt_secret == STRONG


def test_empty_previous_boots() -> None:
    assert _prod(jwt_secret_previous=[]).jwt_secret_previous == []


@pytest.mark.parametrize("secret", [EXAMPLE_JWT_SECRET, "short", ""])
def test_production_refuses_a_bad_current_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET must be"):
        _prod(jwt_secret=secret)


@pytest.mark.parametrize("secret", [EXAMPLE_JWT_SECRET, "short", ""])
def test_production_refuses_a_bad_previous_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_PREVIOUS"):
        _prod(jwt_secret_previous=[OTHER_STRONG, secret])


def test_example_secret_still_works_outside_production() -> None:
    settings = Settings(_env_file=None, environment="dev", jwt_secret=EXAMPLE_JWT_SECRET)  # type: ignore[call-arg]
    assert settings.jwt_secret == EXAMPLE_JWT_SECRET


def test_resend_backend_without_a_key_refuses_to_boot() -> None:
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        _prod(email_backend="resend", resend_api_key=" ")


def test_other_email_backends_do_not_need_a_resend_key() -> None:
    assert _prod(email_backend="smtp").resend_api_key == ""


def test_missing_llm_key_does_not_stop_the_boot() -> None:
    # No setting turns the agent off, so a deploy without it must still start.
    assert _prod().environment == "prod"
