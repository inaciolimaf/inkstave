"""Invite → notification + email hook integration (spec 39, AC2/AC3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.notification import Notification
from inkstave.dependencies import get_email_enqueuer
from inkstave.notifications.service import NotificationService
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


class _FakeEmailEnqueuer:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue_email(self, *, template: str, to: str, context: dict[str, Any]) -> str | None:
        self.calls.append({"template": template, "to": to, "context": context})
        return "job"


@pytest.fixture
def enqueuer(app: Any) -> _FakeEmailEnqueuer:
    fake = _FakeEmailEnqueuer()
    app.dependency_overrides[get_email_enqueuer] = lambda: fake
    return fake


async def _auth(db_session: AsyncSession, email: str | None = None) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session, **({"email": email} if email else {}))
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def test_invite_existing_user_creates_notification_and_email(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: _FakeEmailEnqueuer
) -> None:
    owner, owner_h = await _auth(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    await db_session.commit()
    invitee, _ = await _auth(db_session, email="bob@example.com")

    r = await async_client.post(
        f"{PROJECTS}/{project.id}/invites",
        json={"email": "bob@example.com", "role": "editor"},
        headers=owner_h,
    )
    assert r.status_code == 201
    assert len(enqueuer.calls) == 1  # AC2b: email enqueued
    assert enqueuer.calls[0]["template"] == "project_invite"
    assert enqueuer.calls[0]["context"]["accept_url"].endswith(r.json()["token"])

    notifs = await NotificationService(db_session).list_active(user_id=invitee.id)
    assert len(notifs) == 1  # AC2a: notification created
    notif = notifs[0]
    assert notif.type == "project_invite"
    assert notif.payload["invite_id"] == r.json()["id"]
    assert notif.payload["project_name"] == "Paper"
    assert notif.expires_at is not None and notif.expires_at > datetime.now(UTC)


async def test_invite_unknown_user_email_only(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: _FakeEmailEnqueuer
) -> None:
    owner, owner_h = await _auth(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    await db_session.commit()

    r = await async_client.post(
        f"{PROJECTS}/{project.id}/invites",
        json={"email": "nobody@example.com", "role": "viewer"},
        headers=owner_h,
    )
    assert r.status_code == 201
    assert len(enqueuer.calls) == 1  # AC3: email still enqueued

    total = await db_session.scalar(select(func.count()).select_from(Notification))
    assert total == 0  # no notification for a non-existent user
