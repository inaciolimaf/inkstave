"""Fakes for failure-mode injection (used by readiness tests) — spec 04.

These are plain stub classes (not fixtures). They are re-exported from
``tests/conftest.py`` so existing imports (``from tests.conftest import
FakeEngineBroken``) keep working.
"""

from __future__ import annotations

import asyncio

from redis.exceptions import ConnectionError as RedisConnectionError


class FakeRedisRaising:
    """Stub Redis whose commands raise a real connection error (unreachable server).

    ``ping`` drives the readyz/health failure path; ``zcard``/``llen`` drive the
    metrics queue-depth scrape path (``sample_queue_depth``). All raise the genuine
    ``redis.exceptions.ConnectionError`` so the fail-soft paths exercise a realistic
    connection failure rather than an ``AttributeError`` from a missing method.
    """

    async def ping(self) -> bool:
        raise RedisConnectionError("redis down")

    async def zcard(self, *_args: object, **_kwargs: object) -> int:
        raise RedisConnectionError("redis down")

    async def llen(self, *_args: object, **_kwargs: object) -> int:
        raise RedisConnectionError("redis down")


class FakeRedisHanging:
    """Stub Redis whose ping hangs past any sane timeout."""

    async def ping(self) -> bool:
        await asyncio.sleep(5)
        return True


class _FakeConnection:
    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def execute(self, *_args: object) -> None:
        return None


class FakeEngineOk:
    """Stub async engine whose ``SELECT 1`` succeeds (no real DB)."""

    def connect(self) -> _FakeConnection:
        return _FakeConnection()


class FakeEngineBroken:
    """Stub async engine whose connection attempt fails immediately."""

    def connect(self) -> _FakeConnection:
        raise OSError("database unreachable")
