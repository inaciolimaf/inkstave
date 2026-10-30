"""Unit tests for the plain DI callables (no app/DB needed)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstave.core.db.session import get_session_factory
from inkstave.core.deps import ServiceUnavailableError, get_redis


def _fake_request(**state: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


def test_get_redis_returns_state_client() -> None:
    sentinel = object()
    assert get_redis(_fake_request(redis=sentinel)) is sentinel  # type: ignore[arg-type]


def test_get_redis_missing_raises() -> None:
    with pytest.raises(ServiceUnavailableError):
        get_redis(_fake_request(redis=None))  # type: ignore[arg-type]


def test_get_session_factory_unavailable_raises() -> None:
    with pytest.raises(ServiceUnavailableError):
        get_session_factory(_fake_request(db_sessionmaker=None))  # type: ignore[arg-type]
