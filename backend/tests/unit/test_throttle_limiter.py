"""Unit tests for the throttling limiter: client IP, the stand-down rule and window counters.

No database and no Redis server: fakes from ``_throttle_doubles`` and fakeredis.
"""

from __future__ import annotations

from typing import Any

import pytest

from inkstave.core.errors import RateLimitError
from inkstave.modules.auth.throttling.limiter import (
    _WINDOW_LUA,
    _enforce,
    _identity,
    _submitted_email,
    client_ip,
    hit_window,
    is_public_address,
    peer_counts_ip,
    rate_limit,
)
from tests.unit._throttle_doubles import (
    broken_redis,
    fake_request,
    fallback_redis,
    make_settings,
    no_scripting,
    scripted_redis,
)

# --- client_ip -------------------------------------------------------------------------------


def test_client_ip_without_trusted_headers_is_the_peer() -> None:
    request = fake_request("1.2.3.4", headers={"X-Forwarded-For": "9.9.9.9"})
    assert client_ip(request, make_settings()) == "1.2.3.4"


def test_client_ip_without_a_peer_is_unknown() -> None:
    assert client_ip(fake_request(None), make_settings()) == "unknown"
    assert client_ip(fake_request(None), make_settings(trust_proxy_headers=True)) == "unknown"


def test_client_ip_takes_the_first_hop_of_a_trusted_header() -> None:
    request = fake_request("10.0.0.5", headers={"X-Forwarded-For": " 9.9.9.9 , 10.0.0.5"})
    assert client_ip(request, make_settings(trust_proxy_headers=True)) == "9.9.9.9"


def test_an_empty_trusted_header_falls_back_to_the_peer() -> None:
    request = fake_request("10.0.0.5", headers={"X-Forwarded-For": ""})
    assert client_ip(request, make_settings(trust_proxy_headers=True)) == "10.0.0.5"


# --- the stand-down rule ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "trusted", "expected"),
    [
        ("10.0.0.5", True, True),  # trusted headers: the peer may be counted whatever it is
        ("10.0.0.5", False, False),  # a private peer is the reverse proxy: stand down
        ("8.8.8.8", False, True),  # a public peer is a real client
        ("unknown", False, False),  # no parseable address: stand down
    ],
)
def test_peer_counts_ip(host: str, trusted: bool, expected: bool) -> None:
    settings = make_settings(trust_proxy_headers=trusted)
    assert peer_counts_ip(fake_request(host), settings) is expected


def test_is_public_address_rejects_private_loopback_and_garbage() -> None:
    assert is_public_address("8.8.8.8") is True
    assert is_public_address("10.0.0.5") is False
    assert is_public_address("127.0.0.1") is False
    assert is_public_address("unknown") is False


# --- the counter's identity -------------------------------------------------------------------


async def test_submitted_email_is_trimmed_and_lower_cased() -> None:
    assert await _submitted_email(fake_request(body={"email": "  Ada@Example.COM "}), "register") == (
        "ada@example.com"
    )


@pytest.mark.parametrize("body", [{"name": "Ada"}, [], None])
async def test_submitted_email_is_empty_when_the_body_has_none(body: Any) -> None:
    assert await _submitted_email(fake_request(body=body), "register") == ""


async def test_submitted_email_is_empty_when_the_body_is_not_json() -> None:
    assert await _submitted_email(fake_request(), "register") == ""


async def test_identity_of_an_ordinary_scope_is_the_ip() -> None:
    settings = make_settings()
    assert await _identity(fake_request("8.8.8.8"), "refresh", settings) == "8.8.8.8"


async def test_identity_of_an_ordinary_scope_ignores_the_body_behind_a_proxy() -> None:
    # refresh is not keyed on an e-mail: a private peer stands down, body or not.
    request = fake_request("10.0.0.5", body={"email": "a@x.com"})
    assert await _identity(request, "refresh", make_settings()) is None


async def test_identity_of_forgot_password_behind_a_proxy_is_the_email() -> None:
    request = fake_request("10.0.0.5", body={"email": " A@X.com "})
    assert await _identity(request, "forgot_password", make_settings()) == "email:a@x.com"


async def test_identity_of_forgot_password_behind_a_proxy_without_email_stands_down() -> None:
    assert await _identity(fake_request("10.0.0.5", body={}), "forgot_password", make_settings()) is None


async def test_identity_of_forgot_password_from_a_public_peer_is_the_ip_only() -> None:
    request = fake_request("8.8.8.8", body={"email": "a@x.com"})
    assert await _identity(request, "forgot_password", make_settings()) == "8.8.8.8"


async def test_identity_of_register_from_a_public_peer_is_ip_and_email() -> None:
    request = fake_request("8.8.8.8", body={"email": "a@x.com"})
    assert await _identity(request, "register", make_settings()) == "8.8.8.8:a@x.com"


async def test_identity_of_register_without_an_email_is_the_ip() -> None:
    assert await _identity(fake_request("8.8.8.8", body={}), "register", make_settings()) == "8.8.8.8"


async def test_identity_of_register_behind_a_proxy_is_the_email_alone() -> None:
    request = fake_request("10.0.0.5", body={"email": "a@x.com"})
    assert await _identity(request, "register", make_settings()) == "email:a@x.com"


async def test_identity_of_register_behind_a_proxy_without_email_stands_down() -> None:
    assert await _identity(fake_request("10.0.0.5", body={}), "register", make_settings()) is None


async def test_identity_with_trusted_headers_keys_a_private_peer_by_ip_and_email() -> None:
    request = fake_request("10.0.0.5", body={"email": "a@x.com"})
    settings = make_settings(trust_proxy_headers=True)
    assert await _identity(request, "register", settings) == "10.0.0.5:a@x.com"


# --- hit_window -------------------------------------------------------------------------------


async def test_hit_window_runs_the_window_script_on_the_key() -> None:
    redis = scripted_redis(ttl=42)
    assert await hit_window(redis, "k", 60) == (1, 42)
    assert redis.calls == [(_WINDOW_LUA, 1, "k", "60")]


async def test_hit_window_counts_each_hit_with_a_ttl(redis: Any) -> None:
    fallback = no_scripting(redis)
    assert await hit_window(fallback, "k", 60) == (1, 60)
    assert await hit_window(fallback, "k", 60) == (2, 60)


async def test_fallback_sets_the_expiry_on_the_first_hit_only() -> None:
    redis = fallback_redis(ttl=60)
    await hit_window(redis, "k", 60)
    await hit_window(redis, "k", 60)
    assert redis.expired == [("k", 60)]


async def test_fallback_reads_a_missing_ttl_as_zero() -> None:
    assert await hit_window(fallback_redis(ttl=None), "k", 60) == (1, 0)


async def test_fallback_returns_the_ttl_it_reads() -> None:
    assert await hit_window(fallback_redis(ttl=5), "k", 60) == (1, 5)


# --- _enforce ---------------------------------------------------------------------------------


async def test_enforce_allows_up_to_the_limit_then_refuses() -> None:
    redis = scripted_redis(ttl=37)
    await _enforce(redis, "k", 2, 60)
    await _enforce(redis, "k", 2, 60)
    with pytest.raises(RateLimitError) as exc_info:
        await _enforce(redis, "k", 2, 60)
    assert exc_info.value.headers == {"Retry-After": "37", "X-RateLimit-Remaining": "0"}
    assert redis.calls[-1][3] == "60"


@pytest.mark.parametrize("ttl", [0, -1])
async def test_enforce_retry_after_is_the_window_when_no_ttl_is_left(ttl: int) -> None:
    redis = scripted_redis(ttl=ttl)
    await _enforce(redis, "k", 1, 60)
    with pytest.raises(RateLimitError) as exc_info:
        await _enforce(redis, "k", 1, 60)
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["Retry-After"] == "60"


# --- rate_limit (the dependency) -----------------------------------------------------------


async def test_rate_limit_keys_the_counter_by_scope_and_ip(redis: Any) -> None:
    dep = rate_limit("refresh")
    await dep(fake_request("8.8.8.8"), redis, make_settings(rate_limit_refresh="5/60"))
    assert await redis.exists("ratelimit:refresh:8.8.8.8") == 1


def test_rate_limit_marks_its_scope_for_the_guard_audit() -> None:
    assert rate_limit("refresh").__rate_limit__ == "refresh"  # type: ignore[attr-defined]


async def test_rate_limit_refuses_with_the_window_when_the_ttl_is_gone() -> None:
    dep = rate_limit("refresh")
    settings = make_settings(rate_limit_refresh="1/60")
    redis = scripted_redis(ttl=0)
    await dep(fake_request("8.8.8.8"), redis, settings)
    with pytest.raises(RateLimitError) as exc_info:
        await dep(fake_request("8.8.8.8"), redis, settings)
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["Retry-After"] == "60"


async def test_rate_limit_fails_open_on_a_broken_backend() -> None:
    dep = rate_limit("refresh")
    await dep(fake_request("8.8.8.8"), broken_redis(), make_settings(rate_limit_refresh="1/60"))
