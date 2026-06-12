"""Unit tests for registration schema validation and email normalisation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inkstave.schemas.user import RegisterRequest
from inkstave.services.user import normalise_email


def _valid(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "alice@example.com",
        "password": "secret123",
        "display_name": "Alice",
    }
    base.update(overrides)
    return base


def test_valid_payload_parses() -> None:
    req = RegisterRequest(**_valid())  # type: ignore[arg-type]
    assert req.email == "alice@example.com"
    assert req.display_name == "Alice"


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "abc1"},  # too short
        {"password": "a1" + "x" * 71},  # too long (73)
        {"password": "abcdefgh"},  # no digit
        {"password": "12345678"},  # no letter
        {"password": "alice123"},  # contains email local-part
        {"email": "not-an-email"},  # malformed email
        {"display_name": "   "},  # whitespace-only
        {"display_name": ""},  # empty
    ],
)
def test_invalid_payloads_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(**_valid(**overrides))  # type: ignore[arg-type]


def test_missing_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="alice@example.com", password="secret123")  # type: ignore[call-arg]


def test_display_name_is_trimmed() -> None:
    req = RegisterRequest(**_valid(display_name="  Alice  "))  # type: ignore[arg-type]
    assert req.display_name == "Alice"


def test_email_normalisation() -> None:
    assert normalise_email("  Alice@EX.com ") == "alice@ex.com"
