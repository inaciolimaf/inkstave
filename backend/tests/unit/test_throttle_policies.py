"""Unit tests for the named per-policy limiter: scope keys, counters, headers and fail modes.

No database and no Redis server: fakeredis (which refuses EVAL, so the fallback path runs) and the
doubles in ``_throttle_doubles``. ``time.time`` is pinned so reset values are exact.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Response

from inkstave.core.deps import ServiceUnavailableError
from inkstave.core.errors import RateLimitError
from inkstave.core.observability.metrics import rate_limit_errors
from inkstave.modules.auth.throttling import policies
from inkstave.modules.auth.throttling.policies import (
    RateLimitPolicy,
    RateLimitResult,
    _enforce,
    _raw_ip,
    _scope_id,
    _set_headers,
    check_rate_limit,
    policy_from_setting,
    rate_limit,
    rate_limit_named,
)
from tests.unit._throttle_doubles import (
    broken_redis,
    fake_request,
    fallback_redis,
    make_settings,
    scripted_redis,
)

NOW = 1000.0  # time.time() pinned for every test that reads a reset time


def _policy(key: str = "ip", *, name: str = "t", limit: int = 1, window: int = 60) -> RateLimitPolicy:
    return RateLimitPolicy(name=name, limit=limit, window_seconds=window, key=key)


def _user(user_id: int) -> Any:
    return SimpleNamespace(id=user_id)


@pytest.fixture
def pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policies, "time", SimpleNamespace(time=lambda: NOW))


# --- scope keys -------------------------------------------------------------------------------


def test_raw_ip_is_the_peer_or_unknown() -> None:
    assert _raw_ip(fake_request("8.8.8.8")) == "8.8.8.8"
    assert _raw_ip(fake_request(None)) == "unknown"


def test_ip_policy_keys_on_the_peer_even_when_a_user_is_signed_in() -> None:
    scope = _scope_id(_policy("ip"), fake_request("8.8.8.8"), _user(7), make_settings())
    assert scope == "8.8.8.8"


def test_ip_policy_ignores_a_forged_header_unless_proxy_headers_are_trusted() -> None:
    request = fake_request("8.8.8.8", headers={"X-Forwarded-For": "9.9.9.9"})
    assert _scope_id(_policy("ip"), request, None, make_settings()) == "8.8.8.8"
    trusted = make_settings(trust_proxy_headers=True)
    assert _scope_id(_policy("ip"), request, None, trusted) == "9.9.9.9"


def test_user_policy_keys_on_the_user_and_falls_back_to_the_ip() -> None:
    settings = make_settings()
    assert _scope_id(_policy("user"), fake_request("8.8.8.8"), _user(7), settings) == "user:7"
    assert _scope_id(_policy("user"), fake_request("8.8.8.8"), None, settings) == "ip:8.8.8.8"


def test_user_or_ip_policy_keys_on_the_user_and_falls_back_to_the_ip() -> None:
    settings = make_settings()
    assert _scope_id(_policy("user_or_ip"), fake_request("8.8.8.8"), _user(7), settings) == "user:7"
    assert _scope_id(_policy("user_or_ip"), fake_request("8.8.8.8"), None, settings) == "ip:8.8.8.8"


def test_user_project_policy_keys_on_the_user_and_the_project() -> None:
    request = fake_request("8.8.8.8", path_params={"project_id": "p9"})
    assert _scope_id(_policy("user_project"), request, _user(7), make_settings()) == "user:7:project:p9"


def test_user_project_policy_without_a_user_keys_on_the_ip_and_the_project() -> None:
    request = fake_request("8.8.8.8", path_params={"project_id": "p9"})
    assert _scope_id(_policy("user_project"), request, None, make_settings()) == "ip:8.8.8.8:project:p9"


def test_user_project_policy_without_a_project_id_keys_on_an_empty_project() -> None:
    assert _scope_id(_policy("user_project"), fake_request(), _user(7), make_settings()) == "user:7:project:"


# --- policy_from_setting ----------------------------------------------------------------------


def test_policy_from_setting_reads_limit_and_window() -> None:
    assert policy_from_setting("agent", "10/300", "user") == RateLimitPolicy(
        name="agent", limit=10, window_seconds=300, key="user"
    )


# --- check_rate_limit -------------------------------------------------------------------------


async def test_check_counts_within_the_limit_and_refuses_past_it() -> None:
    redis = scripted_redis(ttl=60)
    policy = _policy("ip", name="t", limit=2)
    first = await check_rate_limit(redis, policy, "1.2.3.4", now=NOW)
    second = await check_rate_limit(redis, policy, "1.2.3.4", now=NOW)
    third = await check_rate_limit(redis, policy, "1.2.3.4", now=NOW)
    assert first == RateLimitResult(allowed=True, limit=2, remaining=1, reset=1060, retry_after=60)
    assert second == RateLimitResult(allowed=True, limit=2, remaining=0, reset=1060, retry_after=60)
    assert third == RateLimitResult(allowed=False, limit=2, remaining=0, reset=1060, retry_after=60)


async def test_check_runs_the_window_script_on_the_policy_key() -> None:
    redis = scripted_redis(ttl=60)
    await check_rate_limit(redis, _policy("ip", name="t"), "1.2.3.4", now=NOW)
    assert [(numkeys, key, window) for _script, numkeys, key, window in redis.calls] == [
        (1, "rl:t:1.2.3.4", "60")
    ]


async def test_check_reports_the_redis_ttl_as_retry_after(redis: Any) -> None:
    # Redis holds a window already: its remaining TTL is what the caller must wait.
    await redis.set("rl:t:1.2.3.4", 1, ex=30)
    result = await check_rate_limit(redis, _policy("ip", limit=1), "1.2.3.4", now=NOW)
    assert result.allowed is False
    assert result.retry_after == 30


async def test_check_fallback_sets_the_window_on_the_first_hit_only() -> None:
    redis = fallback_redis(ttl=45)
    policy = _policy("ip", name="t", limit=5, window=60)
    await check_rate_limit(redis, policy, "1.2.3.4", now=NOW)
    await check_rate_limit(redis, policy, "1.2.3.4", now=NOW)
    assert redis.expired == [("rl:t:1.2.3.4", 60)]


async def test_check_retry_after_is_the_window_when_no_ttl_is_left() -> None:
    result = await check_rate_limit(fallback_redis(ttl=None), _policy(window=60), "x", now=NOW)
    assert result.retry_after == 60


async def test_check_retry_after_is_the_window_on_a_zero_ttl() -> None:
    result = await check_rate_limit(fallback_redis(ttl=0), _policy(window=60), "x", now=NOW)
    assert result.retry_after == 60


async def test_check_accepts_a_remaining_ttl_of_one_second() -> None:
    result = await check_rate_limit(fallback_redis(ttl=1), _policy(window=60), "x", now=NOW)
    assert result.retry_after == 1


async def test_check_reset_is_the_pinned_time_plus_the_ttl() -> None:
    result = await check_rate_limit(fallback_redis(ttl=30), _policy(window=60), "x", now=1000.9)
    assert result.reset == 1030


async def test_check_remaining_never_goes_negative(redis: Any) -> None:
    policy = _policy("ip", limit=1)
    for _ in range(3):
        last = await check_rate_limit(redis, policy, "x", now=NOW)
    assert last.remaining == 0


async def test_the_window_restarts_once_its_key_expires(redis: Any) -> None:
    policy = _policy("ip", limit=1)
    assert (await check_rate_limit(redis, policy, "x", now=NOW)).allowed is True
    assert (await check_rate_limit(redis, policy, "x", now=NOW)).allowed is False
    await redis.delete("rl:t:x")  # what the window's expiry does in Redis
    assert (await check_rate_limit(redis, policy, "x", now=NOW)).allowed is True


# --- _set_headers -----------------------------------------------------------------------------


def test_set_headers_writes_limit_remaining_and_reset() -> None:
    response = Response()
    result = RateLimitResult(allowed=True, limit=5, remaining=3, reset=1060, retry_after=60)
    _set_headers(response, result)
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "3"
    assert response.headers["X-RateLimit-Reset"] == "1060"


# --- _enforce ---------------------------------------------------------------------------------


async def test_enforce_sets_the_headers_and_admits_up_to_the_limit(redis: Any, pinned_clock: None) -> None:
    response = Response()
    policy = _policy("ip", name="t", limit=1)
    await _enforce(redis, response, fake_request("8.8.8.8"), None, make_settings(), policy)
    assert response.headers["X-RateLimit-Limit"] == "1"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["X-RateLimit-Reset"] == "1060"


async def test_enforce_refuses_past_the_limit_with_retry_after(redis: Any, pinned_clock: None) -> None:
    policy = _policy("ip", name="t", limit=1)
    settings = make_settings()
    await _enforce(redis, Response(), fake_request("8.8.8.8"), None, settings, policy)
    with pytest.raises(RateLimitError) as exc_info:
        await _enforce(redis, Response(), fake_request("8.8.8.8"), None, settings, policy)
    assert exc_info.value.headers == {
        "Retry-After": "60",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Limit": "1",
        "X-RateLimit-Reset": "1060",
    }


async def test_enforce_keys_each_client_on_its_own_counter(redis: Any) -> None:
    policy = _policy("ip", name="t", limit=1)
    settings = make_settings()
    await _enforce(redis, Response(), fake_request("8.8.8.8"), None, settings, policy)
    await _enforce(redis, Response(), fake_request("9.9.9.9"), None, settings, policy)  # not refused


async def test_enforce_fails_open_on_a_broken_backend(redis: Any) -> None:
    before = rate_limit_errors.labels(policy="open_test")._value.get()
    response = Response()
    policy = _policy("ip", name="open_test", limit=1)
    await _enforce(broken_redis(), response, fake_request("8.8.8.8"), None, make_settings(), policy)
    assert "X-RateLimit-Limit" not in response.headers
    assert rate_limit_errors.labels(policy="open_test")._value.get() == before + 1


async def test_a_quota_policy_fails_closed_on_a_broken_backend() -> None:
    policy = _policy("user", name="compile_daily", limit=30, window=86400)
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await _enforce(broken_redis(), Response(), fake_request(), _user(7), make_settings(), policy)
    assert exc_info.value.status_code == 503


# --- the dependencies -------------------------------------------------------------------------


def test_rate_limit_dependency_is_marked_with_its_policy_name() -> None:
    assert rate_limit(_policy(name="t")).__rate_limit__ == "t"  # type: ignore[attr-defined]


async def test_rate_limit_dependency_enforces_its_policy(redis: Any) -> None:
    dep = rate_limit(_policy("ip", name="t", limit=1))
    settings = make_settings()
    await dep(fake_request("8.8.8.8"), Response(), None, redis, settings)
    with pytest.raises(RateLimitError):
        await dep(fake_request("8.8.8.8"), Response(), None, redis, settings)


async def test_rate_limit_dependency_is_a_no_op_when_disabled(redis: Any) -> None:
    dep = rate_limit(_policy("ip", name="t", limit=1))
    settings = make_settings(rate_limit_enabled=False)
    response = Response()
    for _ in range(3):
        await dep(fake_request("8.8.8.8"), response, None, redis, settings)
    assert await redis.keys("rl:*") == []
    assert "X-RateLimit-Limit" not in response.headers


async def test_a_fixed_user_policy_counts_each_user_behind_one_address(redis: Any) -> None:
    dep = rate_limit(_policy("user", name="t", limit=1))
    settings = make_settings()
    await dep(fake_request("8.8.8.8"), Response(), _user(1), redis, settings)
    await dep(fake_request("8.8.8.8"), Response(), _user(2), redis, settings)  # another user: admitted
    with pytest.raises(RateLimitError):
        await dep(fake_request("8.8.8.8"), Response(), _user(1), redis, settings)


def test_rate_limit_named_rejects_an_unknown_policy() -> None:
    with pytest.raises(KeyError):
        rate_limit_named("no_such_policy")


def test_rate_limit_named_is_marked_with_its_name() -> None:
    assert rate_limit_named("agent").__rate_limit__ == "agent"  # type: ignore[attr-defined]


async def test_rate_limit_named_reads_its_limit_from_settings(redis: Any, pinned_clock: None) -> None:
    dep = rate_limit_named("agent")
    settings = make_settings(rate_limit_agent="1/60")
    await dep(fake_request("8.8.8.8"), Response(), _user(7), redis, settings)
    with pytest.raises(RateLimitError) as exc_info:
        await dep(fake_request("8.8.8.8"), Response(), _user(7), redis, settings)
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["Retry-After"] == "60"


async def test_a_user_policy_counts_each_user_separately(redis: Any) -> None:
    dep = rate_limit_named("agent")
    settings = make_settings(rate_limit_agent="1/60")
    await dep(fake_request("8.8.8.8"), Response(), _user(1), redis, settings)
    await dep(fake_request("8.8.8.8"), Response(), _user(2), redis, settings)  # another user: admitted


async def test_a_project_policy_counts_each_project_separately(redis: Any) -> None:
    dep = rate_limit_named("chat")
    settings = make_settings(rate_limit_chat="1/60")
    await dep(fake_request(path_params={"project_id": "p1"}), Response(), _user(1), redis, settings)
    await dep(fake_request(path_params={"project_id": "p2"}), Response(), _user(1), redis, settings)
    with pytest.raises(RateLimitError):
        await dep(fake_request(path_params={"project_id": "p1"}), Response(), _user(1), redis, settings)


async def test_a_named_policy_is_a_no_op_when_disabled(redis: Any) -> None:
    dep = rate_limit_named("agent")
    settings = make_settings(rate_limit_agent="1/60", rate_limit_enabled=False)
    for _ in range(3):
        await dep(fake_request("8.8.8.8"), Response(), _user(7), redis, settings)
    assert await redis.keys("rl:*") == []
