"""Opaque single-use tokens: what goes to the user and the hash that is stored."""

from __future__ import annotations

import hashlib
import secrets

_TOKEN_BYTES = 32


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)
