"""Behind an untrusted proxy, no per-IP counter is shared by every user (auth audit).

With ``TRUST_PROXY_HEADERS=false`` and a private peer (the reverse proxy), login already
stands its per-IP limit down and keeps the per-e-mail one. ``refresh``,
``forgot_password`` and ``reset_password`` must follow the same rule: no counter
keyed on the proxy's address, so one user cannot lock out the others.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from inkstave.core.config.settings import get_settings

pytestmark = pytest.mark.integration

AUTH = "/api/v1/auth"


@pytest.fixture
def behind_proxy(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The test client's peer is 127.0.0.1 (private): an untrusted proxy as far as the app knows."""
    get_settings.cache_clear()
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    monkeypatch.setenv("RATE_LIMIT_REFRESH", "1/300")
    monkeypatch.setenv("RATE_LIMIT_AUTH_PASSWORD", "1/3600")
    monkeypatch.setenv("RATE_LIMIT_RESET_PASSWORD", "1/3600")
    yield
    get_settings.cache_clear()


async def test_refresh_does_not_share_one_counter_across_users(
    async_client: AsyncClient, behind_proxy: None
) -> None:
    for index in range(3):
        response = await async_client.post(f"{AUTH}/refresh", json={"refresh_token": f"bogus-{index}"})
        assert response.status_code == 401


async def test_reset_password_does_not_share_one_counter_across_users(
    async_client: AsyncClient, behind_proxy: None
) -> None:
    for index in range(3):
        body = {"token": f"bogus-{index}", "new_password": "Br4ndNewPass"}
        response = await async_client.post(f"{AUTH}/reset-password", json=body)
        assert response.status_code == 400


async def test_forgot_password_is_limited_per_address_not_per_proxy(
    async_client: AsyncClient, behind_proxy: None
) -> None:
    # Different addresses from the same (proxy) peer: no shared counter, all accepted.
    for name in ("a", "b", "c"):
        response = await async_client.post(f"{AUTH}/forgot-password", json={"email": f"{name}@example.com"})
        assert response.status_code == 202

    # The same address is still limited: the per-e-mail half of the rule survives.
    again = await async_client.post(f"{AUTH}/forgot-password", json={"email": "a@example.com"})
    assert again.status_code == 429
