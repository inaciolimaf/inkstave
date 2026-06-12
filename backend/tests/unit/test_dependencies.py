"""Unit tests for the plain DI callables (no app/DB needed)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstave.db.session import get_db_session
from inkstave.dependencies import ServiceUnavailableError, get_redis


def _fake_request(**state: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


def test_get_redis_returns_state_client() -> None:
    sentinel = object()
    assert get_redis(_fake_request(redis=sentinel)) is sentinel  # type: ignore[arg-type]


def test_get_redis_missing_raises() -> None:
    with pytest.raises(ServiceUnavailableError):
        get_redis(_fake_request(redis=None))  # type: ignore[arg-type]


async def test_get_db_session_unavailable_raises() -> None:
    gen = get_db_session(_fake_request(db_sessionmaker=None))  # type: ignore[arg-type]
    with pytest.raises(ServiceUnavailableError):
        await anext(gen)
