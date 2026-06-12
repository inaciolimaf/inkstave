"""Integration tests for the transactional email triggers (spec 103).

Registration → email_verification; forgot-password → password_reset (non-enumerating).
The email enqueuer is a capturing fake (no real ARQ/Redis); no email is sent.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from inkstave.dependencies import get_email_enqueuer

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
FORGOT = "/api/v1/auth/forgot-password"


class FakeEmailEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        self.calls.append({"template": template, "to": to, "context": context})
        return "job"


@pytest.fixture
def emails(app: Any) -> FakeEmailEnqueuer:
    fake = FakeEmailEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: fake
    return fake


async def _register(client: AsyncClient, email: str = "new@example.com") -> None:
    resp = await client.post(
        REGISTER, json={"email": email, "password": "secret123", "display_name": "New"}
    )
    assert resp.status_code == 201, resp.text


async def test_register_enqueues_one_verification_email(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    await _register(async_client, "alice@example.com")
    assert len(emails.calls) == 1
    call = emails.calls[0]
    assert call["template"] == "email_verification"
    assert call["to"] == "alice@example.com"
    assert "/verify-email?token=" in call["context"]["verify_url"]


async def test_forgot_password_unknown_is_non_enumerating(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    resp = await async_client.post(FORGOT, json={"email": "nobody@example.com"})
    assert resp.status_code == 202
    assert emails.calls == []  # no job for an unknown address


async def test_forgot_password_known_enqueues_reset(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    await _register(async_client, "bob@example.com")
    emails.calls.clear()  # drop the verification email from registration

    resp = await async_client.post(FORGOT, json={"email": "bob@example.com"})
    assert resp.status_code == 202
    assert len(emails.calls) == 1
    call = emails.calls[0]
    assert call["template"] == "password_reset"
    assert call["to"] == "bob@example.com"
    assert "/reset-password?token=" in call["context"]["reset_url"]


async def test_forgot_password_same_response_known_or_unknown(
    async_client: AsyncClient, emails: FakeEmailEnqueuer
) -> None:
    await _register(async_client, "carol@example.com")
    known = await async_client.post(FORGOT, json={"email": "carol@example.com"})
    unknown = await async_client.post(FORGOT, json={"email": "ghost@example.com"})
    # Identical status + body so the endpoint can't be used to probe accounts.
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
