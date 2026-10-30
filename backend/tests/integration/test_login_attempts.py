"""Login limits: per e-mail and per IP, wrong passwords only, 429 with Retry-After."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

from inkstave.core.config.settings import get_settings
from inkstave.core.errors import RateLimitError
from inkstave.modules.auth.accounts.login import InvalidCredentialsError
from inkstave.modules.auth.throttling.login_attempts import LoginThrottle

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
EMAIL = "limit@example.com"
PASSWORD = "secret123"


async def _register(client: AsyncClient, email: str = EMAIL) -> None:
    body = {"email": email, "password": PASSWORD, "display_name": "User"}
    assert (await client.post(REGISTER, json=body)).status_code == 201


async def _login(client: AsyncClient, password: str = PASSWORD, email: str = EMAIL) -> Any:
    return await client.post(LOGIN, json={"email": email, "password": password})


def _limits(monkeypatch: pytest.MonkeyPatch, *, email: str = "1000/300", ip: str = "1000/300") -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_LOGIN", email)
    monkeypatch.setenv("RATE_LIMIT_LOGIN_IP", ip)


async def test_the_right_password_is_refused_once_the_email_limit_is_reached(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="2/300")
    await _register(async_client)
    for _ in range(2):
        assert (await _login(async_client, "wrong-pass1")).status_code == 401

    limited = await _login(async_client)

    assert limited.status_code == 429
    assert 0 < int(limited.headers["retry-after"]) <= 300
    assert limited.json()["error"]["type"] == "rate_limited"


async def test_the_email_limit_ignores_case(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="1/300")
    await _login(async_client, "wrong-pass1")

    assert (await _login(async_client, "wrong-pass1", EMAIL.upper())).status_code == 429


async def test_successful_logins_are_not_counted(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="2/300", ip="2/300")
    await _register(async_client)

    for _ in range(5):
        assert (await _login(async_client)).status_code == 200


async def test_success_resets_the_email_counter(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="3/300")
    await _register(async_client)
    for _ in range(2):
        assert (await _login(async_client, "wrong-pass1")).status_code == 401
    assert (await _login(async_client)).status_code == 200

    for _ in range(3):
        assert (await _login(async_client, "wrong-pass1")).status_code == 401


async def test_success_does_not_clear_the_ip_counter(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One valid account must not buy an attacker a fresh allowance of guesses.
    _limits(monkeypatch, ip="2/300")
    await _register(async_client)
    assert (await _login(async_client, "wrong-pass1", "a@example.com")).status_code == 401
    assert (await _login(async_client, "wrong-pass1", "b@example.com")).status_code == 401
    # Third attempt in the window: the IP is over, whichever e-mail it tries.
    assert (await _login(async_client)).status_code == 429


async def test_the_ip_limit_spans_different_emails(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, ip="2/300")
    for name in ("a", "b"):
        assert (await _login(async_client, "wrong-pass1", f"{name}@example.com")).status_code == 401

    limited = await _login(async_client, "wrong-pass1", "c@example.com")

    assert limited.status_code == 429
    assert "retry-after" in limited.headers


async def test_one_locked_email_leaves_the_others_alone(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="1/300")
    await _register(async_client)
    await _login(async_client, "wrong-pass1", "victim@example.com")
    assert (await _login(async_client, "wrong-pass1", "victim@example.com")).status_code == 429

    assert (await _login(async_client)).status_code == 200


async def test_a_concurrent_burst_cannot_outrun_the_limit(redis: Any) -> None:
    settings = get_settings().model_copy(update={"rate_limit_login": "3/300"})
    throttle = LoginThrottle(redis, settings, "198.51.100.1")

    async def guess() -> None:
        async with throttle.attempt(EMAIL):
            await asyncio.sleep(0)  # every guess is in flight before any verify ends
            raise InvalidCredentialsError()

    results = await asyncio.gather(*(guess() for _ in range(10)), return_exceptions=True)

    assert sum(isinstance(result, InvalidCredentialsError) for result in results) == 3
    assert sum(isinstance(result, RateLimitError) for result in results) == 7


async def test_a_redis_failure_while_forgiving_does_not_fail_the_login(
    redis: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    throttle = LoginThrottle(redis, get_settings(), "198.51.100.1")

    async def down(*_args: Any) -> None:
        raise ConnectionError("redis down")

    async with throttle.attempt(EMAIL):
        monkeypatch.setattr(redis, "delete", down)


async def test_disabled_limiter_counts_nothing(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _limits(monkeypatch, email="1/300")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")

    for _ in range(3):
        assert (await _login(async_client, "wrong-pass1")).status_code == 401
