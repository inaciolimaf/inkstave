"""Unit tests for the Redis-backed rate limiter (fakeredis)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from inkstave.auth.rate_limit import client_ip, parse_rate_limit, rate_limit
from inkstave.config import Settings
from inkstave.errors import RateLimitError


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def _request(host: str = "1.2.3.4", headers: dict[str, str] | None = None) -> Any:
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host))


def test_parse_rate_limit() -> None:
    assert parse_rate_limit("10/300") == (10, 300)


def test_client_ip_prefers_trusted_proxy_header() -> None:
    settings = _settings()
    req = _request(headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"})
    assert client_ip(req, settings) == "9.9.9.9"
    assert client_ip(_request(host="5.5.5.5"), settings) == "5.5.5.5"


async def test_limiter_blocks_after_limit(redis: Any) -> None:
    settings = _settings(rate_limit_refresh="2/60")
    dep = rate_limit("refresh")
    req = _request()
    await dep(req, redis, settings)  # 1
    await dep(req, redis, settings)  # 2
    with pytest.raises(RateLimitError) as exc_info:
        await dep(req, redis, settings)  # 3 > 2
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


async def test_limiter_disabled_is_noop(redis: Any) -> None:
    settings = _settings(rate_limit_refresh="1/60", rate_limit_enabled=False)
    dep = rate_limit("refresh")
    req = _request()
    for _ in range(5):
        await dep(req, redis, settings)  # never raises when disabled


async def test_identity_falls_back_to_ip_when_body_unparseable(redis: Any) -> None:
    # login/register identities try to read the email from the body; a body that
    # cannot be parsed must fall back to IP-only keying without raising.
    settings = _settings(rate_limit_login="5/60")
    dep = rate_limit("login")

    class BadBodyRequest:
        headers: dict[str, str] = {}
        client = SimpleNamespace(host="1.2.3.4")

        async def json(self) -> Any:
            raise ValueError("not json")

    await dep(BadBodyRequest(), redis, settings)  # type: ignore[arg-type]
    assert await redis.exists("ratelimit:login:1.2.3.4") == 1


async def test_limiter_fails_open_when_redis_errors() -> None:
    class BrokenRedis:
        async def incr(self, _key: str) -> int:
            raise ConnectionError("redis down")

    settings = _settings(rate_limit_refresh="1/60")
    dep = rate_limit("refresh")
    # Must not raise — a limiter outage fails open.
    await dep(_request(), BrokenRedis(), settings)  # type: ignore[arg-type]
