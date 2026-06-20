"""Daily anti-DoS compile quota (spec 105 §5.5).

The per-user concurrency cap is already covered by test_compile_coordinator.py
(`CompileConcurrencyError`); this asserts the layered 30/user/24h quota.
"""

from __future__ import annotations

from typing import Any

from inkstave.config import Settings
from inkstave.security.rate_limit import (
    _NAMED_POLICIES,
    check_rate_limit,
    policy_from_setting,
)


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


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
    from inkstave.api.routes import compile as compile_routes

    policies = {
        getattr(dep.dependency, "__rate_limit__", None)
        for route in compile_routes.router.routes
        for dep in getattr(route, "dependencies", [])
    }
    assert "compile" in policies
    assert "compile_daily" in policies
