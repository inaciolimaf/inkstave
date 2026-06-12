"""Integration tests for the application lifespan (startup/shutdown wiring).

Redis is faked (a recording stub); the database uses the real test engine so the
engine-create + ``check_db`` + dispose path is exercised. The dispose-on-failure
test guards the fix that the Redis pool is always closed even if DB wiring
raises during startup.
"""

from __future__ import annotations

from typing import Any

import pytest

import inkstave.app as appmod
from inkstave.app import create_app

pytestmark = pytest.mark.integration


class RecordingRedis:
    """Fake Redis recording whether it was closed."""

    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


async def test_lifespan_opens_and_disposes(
    _template_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = RecordingRedis()

    async def _fake_pool(_url: str) -> RecordingRedis:
        return fake

    monkeypatch.setattr(appmod, "create_redis_pool", _fake_pool)
    app = create_app()

    async with appmod.lifespan(app):
        assert app.state.redis is fake
        assert app.state.db_engine is not None
        assert app.state.db_sessionmaker is not None

    assert fake.closed is True
    assert app.state.redis is None
    assert app.state.db_engine is None
    assert app.state.db_sessionmaker is None


async def test_lifespan_disposes_redis_when_db_wiring_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = RecordingRedis()

    async def _fake_pool(_url: str) -> RecordingRedis:
        return fake

    def _boom(_settings: Any) -> Any:
        raise RuntimeError("db wiring failed")

    monkeypatch.setattr(appmod, "create_redis_pool", _fake_pool)
    monkeypatch.setattr(appmod, "create_engine_and_sessionmaker", _boom)
    app = create_app()

    with pytest.raises(RuntimeError, match="db wiring failed"):
        async with appmod.lifespan(app):
            pass

    # The Redis pool must be closed even though DB wiring raised.
    assert fake.closed is True
    assert app.state.redis is None
