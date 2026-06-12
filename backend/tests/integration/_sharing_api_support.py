"""Shared helpers and fixtures for collaborators & sharing integration tests (spec 33).

This module is intentionally not ``test_``-prefixed so pytest does not collect
it. The sibling ``test_sharing_api*.py`` modules import the helpers and the
``enqueuer`` fixture they need from here to stay DRY.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_email_enqueuer
from tests.factories import UserFactory

PROJECTS = "/api/v1/projects"
INVITES = "/api/v1/invites"


class FakeInviteEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        self.calls.append({"template": template, "to": to, "context": context})
        return "job-email"


@pytest.fixture
def enqueuer(app: Any) -> FakeInviteEnqueuer:
    fake = FakeInviteEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: fake
    return fake


async def _auth(db_session: AsyncSession, email: str | None = None) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session, **({"email": email} if email else {}))
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _project(client: AsyncClient, headers: dict[str, str], name: str = "Paper") -> str:
    r = await client.post(PROJECTS, json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _invite(
    client: AsyncClient, headers: dict[str, str], pid: str, email: str, role: str = "editor"
) -> dict[str, Any]:
    r = await client.post(
        f"{PROJECTS}/{pid}/invites", json={"email": email, "role": role}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_member(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_h: dict[str, str],
    pid: str,
    email: str,
    role: str = "editor",
) -> tuple[Any, dict[str, str]]:
    user, headers = await _auth(db_session, email=email)
    token = (await _invite(async_client, owner_h, pid, email, role))["token"]
    await async_client.post(f"{INVITES}/{token}/accept", headers=headers)
    return user, headers
