"""Integration tests for the NotificationService (spec 39)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.notifications.service import NotificationNotFoundError, NotificationService
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _user(db_session: AsyncSession):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    return user


async def test_create_list_and_unread_count(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    svc = NotificationService(db_session)
    await svc.create(user_id=user.id, type="generic", payload={"msg": "one"})
    await svc.create(user_id=user.id, type="generic", payload={"msg": "two"})

    items = await svc.list_active(user_id=user.id)
    assert len(items) == 2  # AC5
    assert await svc.unread_count(user_id=user.id) == 2


async def test_mark_read_and_mark_all(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    svc = NotificationService(db_session)
    a = await svc.create(user_id=user.id, type="generic", payload={})
    await svc.create(user_id=user.id, type="generic", payload={})

    await svc.mark_read(user_id=user.id, notification_id=a.id)
    assert await svc.unread_count(user_id=user.id) == 1  # AC6

    assert await svc.mark_all_read(user_id=user.id) == 1
    assert await svc.unread_count(user_id=user.id) == 0


async def test_dismiss_excludes_from_list(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    svc = NotificationService(db_session)
    n = await svc.create(user_id=user.id, type="generic", payload={})
    await svc.dismiss(user_id=user.id, notification_id=n.id)
    assert await svc.list_active(user_id=user.id) == []  # AC7


async def test_ownership_enforced(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    other = await _user(db_session)
    svc = NotificationService(db_session)
    n = await svc.create(user_id=owner.id, type="generic", payload={})
    with pytest.raises(NotificationNotFoundError):  # AC8
        await svc.mark_read(user_id=other.id, notification_id=n.id)
    with pytest.raises(NotificationNotFoundError):
        await svc.dismiss(user_id=other.id, notification_id=n.id)


async def test_dedupe_invite_notifications(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    svc = NotificationService(db_session)
    await svc.create(
        user_id=user.id,
        type="project_invite",
        payload={"invite_id": "i1", "role": "editor"},
        dedupe_on=("invite_id", "i1"),
    )
    await svc.create(
        user_id=user.id,
        type="project_invite",
        payload={"invite_id": "i1", "role": "viewer"},
        dedupe_on=("invite_id", "i1"),
    )
    items = await svc.list_active(user_id=user.id)
    assert len(items) == 1  # AC4: one active invite notification
    assert items[0].payload["role"] == "viewer"  # the existing row was updated


async def test_dedupe_refresh_resurfaces_notification(db_session: AsyncSession) -> None:
    # spec 40: a re-issued invite (de-dupe path) should bubble back to the top.
    user = await _user(db_session)
    svc = NotificationService(db_session)
    await svc.create(
        user_id=user.id,
        type="project_invite",
        payload={"invite_id": "i1"},
        dedupe_on=("invite_id", "i1"),
    )
    await svc.create(user_id=user.id, type="generic", payload={"msg": "newer"})
    # Re-issue the invite; it must move ahead of the later 'generic' row.
    await svc.create(
        user_id=user.id,
        type="project_invite",
        payload={"invite_id": "i1"},
        dedupe_on=("invite_id", "i1"),
    )
    items = await svc.list_active(user_id=user.id)
    assert items[0].type == "project_invite"  # resurfaced to the top


async def test_expired_excluded_and_swept(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    svc = NotificationService(db_session)
    past = datetime.now(UTC) - timedelta(days=1)
    await svc.create(user_id=user.id, type="generic", payload={}, expires_at=past)
    await svc.create(user_id=user.id, type="generic", payload={})  # no expiry

    assert len(await svc.list_active(user_id=user.id)) == 1  # expired hidden (AC9)

    removed = await svc.sweep_expired()
    assert removed == 1
    assert await svc.sweep_expired() == 0  # idempotent
