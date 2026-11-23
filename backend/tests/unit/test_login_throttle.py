"""Unit tests for the login attempt limits (``LoginThrottle``): what is counted and forgiven.

No database and no Redis server: fakeredis, plus a Redis that is down for the fail-open cases.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from inkstave.core.errors import RateLimitError
from inkstave.core.observability.metrics import rate_limit_errors
from inkstave.modules.auth.accounts.login import InvalidCredentialsError
from inkstave.modules.auth.throttling.login_attempts import LoginThrottle, get_login_throttle
from tests.unit._throttle_doubles import BrokenRedis, fake_request, make_settings

IP_KEY = "ratelimit:login:ip:8.8.8.8"


async def _wrong_password(throttle: LoginThrottle, email: str) -> None:
    """One failed login: the password check raises, the caller sees nothing."""
    with contextlib.suppress(InvalidCredentialsError):
        async with throttle.attempt(email):
            raise InvalidCredentialsError()


async def _right_password(throttle: LoginThrottle, email: str) -> None:
    async with throttle.attempt(email):
        pass


async def test_the_email_limit_admits_up_to_the_limit_then_refuses(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="2/60"), "8.8.8.8")
    await _wrong_password(throttle, "ada@example.com")
    await _wrong_password(throttle, "ada@example.com")
    with pytest.raises(RateLimitError) as exc_info:
        await _wrong_password(throttle, "ada@example.com")
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["Retry-After"] == "60"


async def test_a_refused_attempt_never_runs_the_password_check(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="1/60"), "8.8.8.8")
    await _wrong_password(throttle, "ada@example.com")
    checked: list[bool] = []
    with pytest.raises(RateLimitError):
        async with throttle.attempt("ada@example.com"):
            checked.append(True)
    assert checked == []


async def test_the_email_counter_ignores_case_and_surrounding_spaces(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="2/60"), "8.8.8.8")
    await _wrong_password(throttle, "Ada@Example.com")
    await _wrong_password(throttle, " ada@example.com ")
    assert await redis.exists("ratelimit:login:email:ada@example.com") == 1
    with pytest.raises(RateLimitError):
        await _wrong_password(throttle, "ADA@example.com")


async def test_a_successful_login_clears_the_email_counter(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="3/60"), "8.8.8.8")
    await _wrong_password(throttle, "ada@example.com")
    await _wrong_password(throttle, "ada@example.com")
    await _right_password(throttle, "ada@example.com")
    assert await redis.exists("ratelimit:login:email:ada@example.com") == 0
    for _ in range(3):
        await _wrong_password(throttle, "ada@example.com")
    with pytest.raises(RateLimitError):
        await _wrong_password(throttle, "ada@example.com")


async def test_a_locked_out_email_refuses_even_the_right_password(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="2/60"), "8.8.8.8")
    await _wrong_password(throttle, "ada@example.com")
    await _wrong_password(throttle, "ada@example.com")
    with pytest.raises(RateLimitError):
        await _right_password(throttle, "ada@example.com")


async def test_an_error_other_than_a_wrong_password_is_forgiven(redis: Any) -> None:
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="5/60"), "8.8.8.8")
    await _wrong_password(throttle, "ada@example.com")
    with pytest.raises(RuntimeError):
        async with throttle.attempt("ada@example.com"):
            raise RuntimeError("the account service broke")
    assert await redis.exists("ratelimit:login:email:ada@example.com") == 0


async def test_a_disabled_limiter_never_refuses_or_counts(redis: Any) -> None:
    throttle = LoginThrottle(
        redis, make_settings(rate_limit_login="1/60", rate_limit_enabled=False), "8.8.8.8"
    )
    for _ in range(5):
        await _wrong_password(throttle, "ada@example.com")
    assert await redis.keys("ratelimit:login:*") == []


async def test_a_public_peer_is_limited_per_ip_across_emails(redis: Any) -> None:
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="2/60")
    throttle = LoginThrottle(redis, settings, "8.8.8.8")
    await _wrong_password(throttle, "a@example.com")
    await _wrong_password(throttle, "b@example.com")
    assert await redis.get(IP_KEY) == b"2"
    with pytest.raises(RateLimitError):
        await _wrong_password(throttle, "c@example.com")


async def test_a_private_peer_without_trusted_headers_is_not_counted_per_ip(redis: Any) -> None:
    # The peer is the reverse proxy: an IP counter would lock every user out with one user's failures.
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="2/60")
    throttle = LoginThrottle(redis, settings, "10.0.0.5")
    for index in range(5):
        await _wrong_password(throttle, f"user{index}@example.com")
    assert await redis.keys("ratelimit:login:ip:*") == []


async def test_trusted_headers_count_a_private_peer_per_ip(redis: Any) -> None:
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="2/60", trust_proxy_headers=True)
    throttle = LoginThrottle(redis, settings, "10.0.0.5")
    await _wrong_password(throttle, "a@example.com")
    await _wrong_password(throttle, "b@example.com")
    with pytest.raises(RateLimitError):
        await _wrong_password(throttle, "c@example.com")


async def test_a_success_forgives_only_its_own_hit_on_the_ip(redis: Any) -> None:
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="50/60")
    throttle = LoginThrottle(redis, settings, "8.8.8.8")
    await _wrong_password(throttle, "a@example.com")
    await _wrong_password(throttle, "b@example.com")
    await _right_password(throttle, "a@example.com")
    assert int(await redis.get(IP_KEY)) == 2  # a's earlier failure and b's failure still count


async def test_the_ip_counter_keeps_an_earlier_failure_after_a_success(redis: Any) -> None:
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="50/60")
    throttle = LoginThrottle(redis, settings, "8.8.8.8")
    await _wrong_password(throttle, "a@example.com")
    await _right_password(throttle, "a@example.com")
    assert int(await redis.get(IP_KEY)) == 1


async def test_a_lone_success_leaves_no_ip_counter(redis: Any) -> None:
    settings = make_settings(rate_limit_login="50/60", rate_limit_login_ip="50/60")
    await _right_password(LoginThrottle(redis, settings, "8.8.8.8"), "a@example.com")
    assert await redis.exists(IP_KEY) == 0


async def test_a_redis_outage_fails_open_counts_a_metric_and_forgives_nothing() -> None:
    class _OutageRecordingDeletes(BrokenRedis):
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete(self, *keys: str) -> int:
            self.deleted.extend(keys)
            return await super().delete(*keys)

    redis: Any = _OutageRecordingDeletes()
    before = rate_limit_errors.labels(policy="login")._value.get()
    throttle = LoginThrottle(redis, make_settings(rate_limit_login="1/60"), "8.8.8.8")
    await _right_password(throttle, "a@example.com")  # admitted: the limiter is down
    with pytest.raises(InvalidCredentialsError):
        async with throttle.attempt("a@example.com"):  # still admitted, and never counted
            raise InvalidCredentialsError()
    assert redis.deleted == []  # an attempt that was never counted is not forgiven
    assert rate_limit_errors.labels(policy="login")._value.get() == before + 2


async def test_get_login_throttle_keys_on_the_address_of_the_request(redis: Any) -> None:
    throttle = get_login_throttle(fake_request("8.8.8.8"), redis, make_settings())
    await _wrong_password(throttle, "a@example.com")
    assert await redis.exists(IP_KEY) == 1


async def test_get_login_throttle_takes_the_forwarded_address_when_trusted(redis: Any) -> None:
    settings = make_settings(trust_proxy_headers=True)
    request = fake_request("10.0.0.5", headers={"X-Forwarded-For": "8.8.8.8"})
    await _wrong_password(get_login_throttle(request, redis, settings), "a@example.com")
    assert await redis.exists(IP_KEY) == 1


def test_get_login_throttle_is_marked_as_the_login_scope() -> None:
    assert get_login_throttle.__rate_limit__ == "login"  # type: ignore[attr-defined]
