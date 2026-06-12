"""Integration tests for collaborators & sharing (spec 33): member management.

Covers role changes, member removal, the owner-cannot-leave guard and ownership
transfer. Shared helpers and the ``enqueuer`` fixture live in
``_sharing_api_support``.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.membership import ProjectMembership

from ._sharing_api_support import (
    PROJECTS,
    FakeInviteEnqueuer,
    _add_member,
    _auth,
    _project,
    enqueuer,
)

pytestmark = pytest.mark.integration

__all__ = ["enqueuer"]


# --- member management ----------------------------------------------------- #


async def test_change_role_and_owner_rejected(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    bob, _ = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", "editor")

    r = await async_client.patch(
        f"{PROJECTS}/{pid}/members/{bob.id}", json={"role": "viewer"}, headers=owner_h
    )
    assert r.status_code == 200 and r.json()["role"] == "viewer"  # AC5

    bad = await async_client.patch(
        f"{PROJECTS}/{pid}/members/{bob.id}", json={"role": "owner"}, headers=owner_h
    )
    assert bad.status_code == 400  # cannot PATCH to owner


async def test_remove_member(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    bob, _ = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")

    r = await async_client.delete(f"{PROJECTS}/{pid}/members/{bob.id}", headers=owner_h)
    assert r.status_code == 204  # AC6
    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    assert all(m["user_id"] != str(bob.id) for m in members)


async def test_owner_cannot_leave(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    r = await async_client.delete(f"{PROJECTS}/{pid}/members/{owner.id}", headers=owner_h)
    assert r.status_code == 400 and r.json()["error"]["type"] == "owner_cannot_leave"  # AC7


async def test_transfer_ownership_single_owner(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    bob, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")

    r = await async_client.post(
        f"{PROJECTS}/{pid}/members/transfer", json={"to_user_id": str(bob.id)}, headers=owner_h
    )
    assert r.status_code == 200 and r.json()["role"] == "owner"  # AC8

    members = (await async_client.get(f"{PROJECTS}/{pid}/members", headers=bob_h)).json()
    owners = [m for m in members if m["role"] == "owner"]
    assert len(owners) == 1 and owners[0]["user_id"] == str(bob.id)  # exactly one owner
    prev = next(m for m in members if m["user_id"] == str(owner.id))
    assert prev["role"] == "editor"  # previous owner demoted

    # The new owner is reflected on the project row too.
    project_owner = (
        await db_session.execute(
            select(ProjectMembership.user_id).where(
                ProjectMembership.project_id == UUID(pid),
                ProjectMembership.role == "owner",
            )
        )
    ).scalar_one()
    assert project_owner == bob.id
