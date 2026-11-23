"""Doubles for the throttling unit tests (spec 52, mutation hardening).

Plain stand-ins for the parts of Starlette and Redis the limiters read. They are helpers, not
tests: the test modules import them.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from redis.exceptions import ResponseError

from inkstave.core.config.settings import Settings

_NO_BODY = object()


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


class FakeRequest:
    """The request attributes the limiters read: headers, peer, path params and a JSON body."""

    def __init__(
        self,
        host: str | None = "1.2.3.4",
        *,
        headers: dict[str, str] | None = None,
        body: Any = _NO_BODY,
        path_params: dict[str, str] | None = None,
    ) -> None:
        self.headers = headers or {}
        self.client = None if host is None else SimpleNamespace(host=host)
        self.path_params = path_params or {}
        self._body = body

    async def json(self) -> Any:
        if self._body is _NO_BODY:
            raise ValueError("no JSON body")
        return self._body


class ScriptedRedis:
    """Redis with server-side scripting: records every EVAL and answers ``[count, ttl]``.

    The counter goes up on each EVAL of a key, and every answer carries the same ``ttl``.
    """

    def __init__(self, ttl: int = 60) -> None:
        self.ttl = ttl
        self.calls: list[tuple[Any, ...]] = []
        self.counts: dict[str, int] = {}

    async def eval(self, script: str, numkeys: int, key: str, window: str) -> list[int]:
        self.calls.append((script, numkeys, key, window))
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], self.ttl]


class NoScriptingRedis:
    """Wraps a real (fake) Redis that refuses EVAL, as fakeredis does: the fallback path runs."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def eval(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ResponseError("unknown command 'eval'")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class FallbackRedis:
    """Redis without scripting whose TTL answer the test sets; records every EXPIRE."""

    def __init__(self, ttl: int | None) -> None:
        self.ttl_answer = ttl
        self.expired: list[tuple[str, int]] = []
        self.count = 0

    async def eval(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ResponseError("unknown command 'eval'")

    async def incr(self, _key: str) -> int:
        self.count += 1
        return self.count

    async def expire(self, key: str, seconds: int) -> None:
        self.expired.append((key, seconds))

    async def ttl(self, _key: str) -> int | None:
        return self.ttl_answer


class BrokenRedis:
    """Every command fails as an unreachable server would: the limiters must fail open."""

    async def eval(self, *_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError("redis down")

    async def incr(self, _key: str) -> int:
        raise ConnectionError("redis down")

    async def delete(self, *_keys: str) -> int:
        raise ConnectionError("redis down")

    async def decr(self, _key: str) -> int:
        raise ConnectionError("redis down")


# Factories typed ``Any``: the limiters are typed for the real Starlette request and Redis client,
# and a double passed to them would fail the strict type check of the test tree.


def fake_request(
    host: str | None = "1.2.3.4",
    *,
    headers: dict[str, str] | None = None,
    body: Any = _NO_BODY,
    path_params: dict[str, str] | None = None,
) -> Any:
    return FakeRequest(host, headers=headers, body=body, path_params=path_params)


def scripted_redis(ttl: int = 60) -> Any:
    return ScriptedRedis(ttl)


def fallback_redis(ttl: int | None) -> Any:
    return FallbackRedis(ttl)


def no_scripting(inner: Any) -> Any:
    return NoScriptingRedis(inner)


def broken_redis() -> Any:
    return BrokenRedis()
