"""Daily anti-DoS compile quota (spec 105 §5.5).

The per-user concurrency cap is already covered by test_compile_coordinator.py
(`CompileConcurrencyError`); this asserts the layered 30/user/24h quota.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Response

from inkstave.core.config.settings import Settings
from inkstave.core.deps import ServiceUnavailableError
from inkstave.modules.auth.throttling.policies import (
    _NAMED_POLICIES,
    _enforce,
    check_rate_limit,
    policy_from_setting,
)


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_compile_daily_policy_is_registered_and_defaults_to_30_per_day() -> None:
    assert "compile_daily" in _NAMED_POLICIES
    attr, key = _NAMED_POLICIES["compile_daily"]
    assert attr == "rate_limit_compile_daily" and key == "user"
    s = _settings()
    policy = policy_from_setting("compile_daily", s.rate_limit_compile_daily, key)
    assert policy.limit == 30
    assert policy.window_seconds == 86_400  # 24h window


async def test_thirty_first_compile_in_the_window_is_blocked(redis: Any) -> None:
    s = _settings()
    policy = policy_from_setting("compile_daily", s.rate_limit_compile_daily, "user")
    scope = "user:11111111-1111-1111-1111-111111111111"

    for _ in range(30):
        result = await check_rate_limit(redis, policy, scope, now=1000.0)
        assert result.allowed is True

    # The 31st within the same 24h window is refused, with a positive Retry-After.
    blocked = await check_rate_limit(redis, policy, scope, now=1000.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after > 0


async def test_quota_is_scoped_per_user(redis: Any) -> None:
    s = _settings(rate_limit_compile_daily="1/86400")
    policy = policy_from_setting("compile_daily", s.rate_limit_compile_daily, "user")

    a = await check_rate_limit(redis, policy, "user:aaaa", now=0.0)
    b = await check_rate_limit(redis, policy, "user:bbbb", now=0.0)
    assert a.allowed and b.allowed  # different users do not share the counter

    a2 = await check_rate_limit(redis, policy, "user:aaaa", now=0.0)
    assert a2.allowed is False  # the same user's 2nd over a 1/day cap is blocked


def test_compile_route_attaches_the_daily_quota_dependency() -> None:
    # The POST .../compile route must carry both the per-minute and the daily caps.
    from inkstave.modules.compile.routes import compile as compile_routes

    policies = {
        getattr(dep.dependency, "__rate_limit__", None)
        for route in compile_routes.router.routes
        for dep in getattr(route, "dependencies", [])
    }
    assert "compile" in policies
    assert "compile_daily" in policies


class _RedisDown:
    async def eval(self, *_args: Any, **_kwargs: Any) -> None:
        raise ConnectionError("redis is down")


async def test_daily_quota_fails_closed_when_redis_is_down() -> None:
    # A limiter outage must not lift the daily cap: the compile is refused, not run unthrottled.
    s = _settings()
    policy = policy_from_setting("compile_daily", s.rate_limit_compile_daily, "user")
    request = SimpleNamespace(client=None, headers={}, path_params={})
    user = SimpleNamespace(id="11111111-1111-1111-1111-111111111111")

    with pytest.raises(ServiceUnavailableError):
        await _enforce(_RedisDown(), Response(), request, user, s, policy)  # type: ignore[arg-type]  # a stand-in for the real argument; the test exercises the runtime path
