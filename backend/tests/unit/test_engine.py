"""Unit tests for engine/sessionmaker construction (no DB connection opened)."""

from __future__ import annotations

import pytest

from inkstave.config import Settings
from inkstave.db.engine import create_engine_and_sessionmaker


async def test_create_engine_and_sessionmaker_uses_async_driver(
    settings_override: Settings,
) -> None:
    # create_async_engine is lazy — no connection is opened here.
    engine, sessionmaker = create_engine_and_sessionmaker(settings_override)
    try:
        assert engine.url.drivername == "postgresql+asyncpg"
        assert sessionmaker is not None
    finally:
        await engine.dispose()


def test_create_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url is None
    with pytest.raises(ValueError, match="database_url"):
        create_engine_and_sessionmaker(settings)
