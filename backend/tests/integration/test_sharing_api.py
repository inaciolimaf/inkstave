"""Integration tests for collaborators & sharing (spec 33): invite lifecycle.

Shared helpers and the ``enqueuer`` fixture live in ``_sharing_api_support``.
Sibling modules (``test_sharing_api_members`` and ``test_sharing_api_authz``)
cover member management/ownership transfer and authorization concerns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.invite import ProjectInvite

from ._sharing_api_support import (
    INVITES,
    PROJECTS,
    FakeInviteEnqueuer,
    _auth,
    _invite,
    _project,
    enqueuer,
)

pytestmark = pytest.mark.integration

__all__ = ["enqueuer"]


# --- invite lifecycle ------------------------------------------------------ #


async def test_invite_create_enqueues_and_lists(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)

    invite = await _invite(async_client, owner_h, pid, "bob@example.com", "editor")
    assert invite["status"] == "pending"
    assert invite["role"] == "editor"
    assert invite["token"]  # raw token returned to the inviter
    assert len(enqueuer.calls) == 1  # email job enqueued (AC1)

    listed = (await async_client.get(f"{PROJECTS}/{pid}/invites", headers=owner_h)).json()
    assert [i["email"] for i in listed] == ["bob@example.com"]
    assert "token" not in listed[0]  # raw token never leaked in the list


async def test_accept_creates_membership_and_is_idempotent(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, bob_h = await _auth(db_session, email="bob@example.com")
    token = (await _invite(async_client, owner_h, pid, "bob@example.com", "editor"))["token"]

    r = await async_client.post(f"{INVITES}/{token}/accept", headers=bob_h)
    assert r.status_code == 200
    assert r.json() == {"project_id": pid, "role": "editor"}

    # Idempotent re-accept (AC2).
    r2 = await async_client.post(f"{INVITES}/{token}/accept", headers=bob_h)
    assert r2.status_code == 200

    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    assert len(members) == 2  # owner + bob, not duplicated by the re-accept
    bob = next(m for m in members if m["email"] == "bob@example.com")
    assert bob["role"] == "editor" and bob["status"] == "active"


async def test_decline_creates_no_membership(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, bob_h = await _auth(db_session, email="bob@example.com")
    token = (await _invite(async_client, owner_h, pid, "bob@example.com"))["token"]

    r = await async_client.post(f"{INVITES}/{token}/decline", headers=bob_h)
    assert r.status_code == 204

    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    assert all(m["email"] != "bob@example.com" for m in members)  # AC3


async def test_expired_invite_returns_410(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, bob_h = await _auth(db_session, email="bob@example.com")
    token = (await _invite(async_client, owner_h, pid, "bob@example.com"))["token"]

    # Force expiry directly in the DB.
    await db_session.execute(
        update(ProjectInvite).values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    r = await async_client.post(f"{INVITES}/{token}/accept", headers=bob_h)
    assert r.status_code == 410  # AC4
    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    assert all(m["email"] != "bob@example.com" for m in members)


async def test_expired_invite_decline_returns_410(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, bob_h = await _auth(db_session, email="bob@example.com")
    token = (await _invite(async_client, owner_h, pid, "bob@example.com"))["token"]

    # Force expiry directly in the DB.
    await db_session.execute(
        update(ProjectInvite).values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    r = await async_client.post(f"{INVITES}/{token}/decline", headers=bob_h)
    assert r.status_code == 410  # AC4 — decline path
    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    assert all(m["email"] != "bob@example.com" for m in members)  # no membership created


async def test_reinvite_refreshes_pending(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    await _invite(async_client, owner_h, pid, "bob@example.com", "editor")
    await _invite(async_client, owner_h, pid, "bob@example.com", "viewer")  # refresh

    listed = (await async_client.get(f"{PROJECTS}/{pid}/invites", headers=owner_h)).json()
    assert len(listed) == 1  # single pending invite, refreshed not duplicated
    assert listed[0]["role"] == "viewer"


async def test_revoke_invite(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    invite = await _invite(async_client, owner_h, pid, "bob@example.com")

    r = await async_client.delete(f"{PROJECTS}/{pid}/invites/{invite['id']}", headers=owner_h)
    assert r.status_code == 204
    listed = (await async_client.get(f"{PROJECTS}/{pid}/invites", headers=owner_h)).json()
    assert listed == []
