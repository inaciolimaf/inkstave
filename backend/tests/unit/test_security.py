"""Unit tests for security hardening: limiter, uploads, headers, guards (spec 52)."""

from __future__ import annotations

from typing import Any

import pytest

from inkstave.config import Settings
from inkstave.security.rate_limit import RateLimitPolicy, check_rate_limit
from inkstave.security.uploads import (
    content_matches_extension,
    extension_allowed,
    sanitize_filename,
)


def _settings(**over: Any) -> Settings:
    # Use a non-default redis_url: the production boot guard (config.py) treats the
    # localhost default as "unset" in prod, so the "prod boots" case below needs a
    # real-looking value to exercise the JWT/CORS guards rather than tripping REDIS.
    base = {"jwt_secret": "x" * 40, "redis_url": "redis://redis:6379/0"}
    return Settings(**{**base, **over})  # type: ignore[arg-type]


# --- rate limiter (fakeredis) ----------------------------------------------- #


@pytest.mark.integration
async def test_limiter_allows_then_blocks_then_resets(redis: Any) -> None:
    policy = RateLimitPolicy(name="t", limit=2, window_seconds=60, key="ip")
    r1 = await check_rate_limit(redis, policy, "1.2.3.4", now=1000.0)
    r2 = await check_rate_limit(redis, policy, "1.2.3.4", now=1000.0)
    r3 = await check_rate_limit(redis, policy, "1.2.3.4", now=1000.0)
    assert r1.allowed and r1.remaining == 1
    assert r2.allowed and r2.remaining == 0
    assert not r3.allowed and r3.remaining == 0 and r3.retry_after > 0
    # A different scope has its own independent window.
    other = await check_rate_limit(redis, policy, "9.9.9.9", now=1000.0)
    assert other.allowed


# --- upload sanitization ----------------------------------------------------- #


def test_sanitize_filename_strips_traversal_nul_and_charset() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/abs/path/img.png") == "img.png"
    assert sanitize_filename("a\\b\\win.png") == "win.png"
    assert sanitize_filename("ev\x00il.png") == "evil.png"
    assert sanitize_filename("...hidden") == "hidden"
    assert sanitize_filename("we!rd*na/me.tex") == "me.tex"
    assert sanitize_filename("") == "file"
    assert len(sanitize_filename("a" * 400 + ".png")) <= 255


def test_extension_allow_list_and_content_match() -> None:
    allowed = [".png", ".tex", ".pdf"]
    assert extension_allowed("img.PNG", allowed)
    assert not extension_allowed("evil.exe", allowed)
    # a .png must sniff as PNG; a text extension has no binary signature to enforce.
    assert content_matches_extension("img.png", "image/png")
    assert not content_matches_extension("img.png", "application/pdf")
    assert content_matches_extension("refs.bib", "application/octet-stream")


# --- secret boot guard ------------------------------------------------------- #


def test_production_secret_guard() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _settings(environment="prod", jwt_secret="changeme", cors_origins=["https://a.com"])
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _settings(environment="prod", jwt_secret="short", cors_origins=["https://a.com"])
    # A strong secret in prod boots.
    _settings(environment="prod", jwt_secret="z" * 48, cors_origins=["https://a.com"])
    # dev/test allow a weak secret.
    _settings(environment="dev", jwt_secret="dev")


def test_cors_guard_rejects_wildcard_and_empty_prod() -> None:
    with pytest.raises(ValueError, match="CORS allow-list cannot be"):
        _settings(cors_origins=["*"])
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS must be set"):
        _settings(environment="prod", jwt_secret="z" * 48, cors_origins=[])


# --- dependency audit gate (AC11; fast, no network) ------------------------- #


def test_audit_script_exists_and_runs_both_tools() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[2].parent / "scripts" / "audit.sh"
    assert script.is_file()
    body = script.read_text()
    assert "pip-audit" in body
    assert "npm audit --audit-level=high" in body
    assert "audit-allowlist.txt" in body  # an allowlist mechanism is wired
