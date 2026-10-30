"""The suite never reads the machine's configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.config import Settings, get_settings
from tests.fixtures.env import UNREACHABLE_DATABASE_URL


def test_dotenv_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("REDIS_URL=redis://from-the-machine\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert Settings().redis_url != "redis://from-the-machine"


def test_database_is_unreachable_unless_a_test_asks_for_it() -> None:
    assert get_settings().database_url == UNREACHABLE_DATABASE_URL
