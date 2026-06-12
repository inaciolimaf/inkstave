"""Integration tests for the notification endpoints (spec 39)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.notifications.service import NotificationService
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

NOTIFS = "/api/v1/notifications"


async def _auth(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _notify(db_session: AsyncSession, user_id: Any, **payload: Any) -> Any:
    n = await NotificationService(db_session).create(
        user_id=user_id, type="generic", payload=payload
    )
    await db_session.commit()
    return n


async def test_list_and_unread_count(async_client: AsyncClient, db_session: AsyncSession) -> None:
    user, headers = await _auth(db_session)
    await _notify(db_session, user.id, msg="a")
    await _notify(db_session, user.id, msg="b")

    body = (await async_client.get(NOTIFS, headers=headers)).json()
    assert len(body["items"]) == 2 and body["unread_count"] == 2  # AC5
    count = (await async_client.get(f"{NOTIFS}/unread-count", headers=headers)).json()
    assert count == {"count": 2}


async def test_mark_read_read_all_and_dismiss(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user, headers = await _auth(db_session)
    a = await _notify(db_session, user.id, msg="a")
    await _notify(db_session, user.id, msg="b")

    r = await async_client.post(f"{NOTIFS}/{a.id}/read", headers=headers)
    assert r.status_code == 200 and r.json()["read_at"] is not None  # AC6
    assert (await async_client.get(f"{NOTIFS}/unread-count", headers=headers)).json()["count"] == 1

    all_read = await async_client.post(f"{NOTIFS}/read-all", headers=headers)
    assert all_read.json() == {"updated": 1}

    dismissed = await async_client.delete(f"{NOTIFS}/{a.id}", headers=headers)
    assert dismissed.status_code == 204  # AC7
    listed = (await async_client.get(NOTIFS, headers=headers)).json()["items"]
    assert all(item["id"] != str(a.id) for item in listed)


async def test_cross_user_404(async_client: AsyncClient, db_session: AsyncSession) -> None:
    owner, _ = await _auth(db_session)
    _other, other_h = await _auth(db_session)
    n = await _notify(db_session, owner.id, msg="secret")
    n_id = str(n.id)  # capture before the 404 rolls back + expires the ORM object

    assert (await async_client.post(f"{NOTIFS}/{n_id}/read", headers=other_h)).status_code == 404
    deleted = await async_client.delete(f"{NOTIFS}/{n_id}", headers=other_h)
    assert deleted.status_code == 404  # AC8
