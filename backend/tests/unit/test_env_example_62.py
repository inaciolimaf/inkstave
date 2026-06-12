"""Spec 62 AC6: `.env.example` parses cleanly with no duplicate keys."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

# repo root = .../inkstave ; this file is backend/tests/unit/test_env_example_62.py
_ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def _keys() -> list[str]:
    keys: list[str] = []
    for raw in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.split("=", 1)[0].strip())
    return keys


def test_env_example_has_no_duplicate_keys() -> None:
    keys = _keys()
    duplicates = {key: count for key, count in Counter(keys).items() if count > 1}
    assert duplicates == {}, f"duplicate keys in .env.example: {duplicates}"


def test_cors_and_upload_appear_exactly_once() -> None:
    counts = Counter(_keys())
    assert counts["CORS_ORIGINS"] == 1
    assert counts["MAX_UPLOAD_BYTES"] == 1
