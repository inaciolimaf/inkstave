"""Unit tests for the argon2 password-hashing service."""

from __future__ import annotations

from inkstave.auth.password import build_password_hasher
from inkstave.config import Settings


def test_hash_is_phc_string_and_not_plaintext(settings_override: Settings) -> None:
    hasher = build_password_hasher(settings_override)
    hashed = hasher.hash("secret123")
    assert hashed.startswith("$argon2id$")
    assert hashed != "secret123"


def test_verify_true_for_correct_password(settings_override: Settings) -> None:
    hasher = build_password_hasher(settings_override)
    hashed = hasher.hash("secret123")
    assert hasher.verify("secret123", hashed) is True


def test_verify_false_for_wrong_password(settings_override: Settings) -> None:
    hasher = build_password_hasher(settings_override)
    hashed = hasher.hash("secret123")
    assert hasher.verify("wrongpass1", hashed) is False


def test_verify_false_for_garbage_hash_without_raising(settings_override: Settings) -> None:
    hasher = build_password_hasher(settings_override)
    assert hasher.verify("secret123", "not-a-real-hash") is False
    assert hasher.verify("secret123", "") is False
