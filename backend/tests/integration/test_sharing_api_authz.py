"""Integration tests for collaborators & sharing (spec 33): authorization.

Covers the owner-only endpoint 403 sweep, the already-member conflict and
cross-project isolation. Shared helpers and the ``enqueuer`` fixture live in
``_sharing_api_support``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


# --- authorization --------------------------------------------------------- #


async def test_non_owner_owner_only_endpoints_403(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    bob, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")
    carol, _ = await _add_member(async_client, db_session, owner_h, pid, "carol@example.com")
    bob_id = str(bob.id)  # capture before any 403 rolls back + expires the ORM object
    carol_id = str(carol.id)

    # AC9: an editor member hits owner-only endpoints -> 403.
    assert (
        await async_client.post(
            f"{PROJECTS}/{pid}/invites", json={"email": "x@example.com", "role": "viewer"},
            headers=bob_h,
        )
    ).status_code == 403
    assert (await async_client.get(f"{PROJECTS}/{pid}/invites", headers=bob_h)).status_code == 403
    assert (
        await async_client.patch(
            f"{PROJECTS}/{pid}/members/{bob_id}", json={"role": "viewer"}, headers=bob_h
        )
    ).status_code == 403
    # Remove-other and transfer are owner-only too.
    assert (
        await async_client.delete(f"{PROJECTS}/{pid}/members/{carol_id}", headers=bob_h)
    ).status_code == 403
    assert (
        await async_client.post(
            f"{PROJECTS}/{pid}/members/transfer", json={"to_user_id": carol_id}, headers=bob_h
        )
    ).status_code == 403
    # But a member CAN list members.
    assert (await async_client.get(f"{PROJECTS}/{pid}/members", headers=bob_h)).status_code == 200


async def test_invite_already_member_409(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")

    r = await async_client.post(
        f"{PROJECTS}/{pid}/invites", json={"email": "bob@example.com", "role": "viewer"},
        headers=owner_h,
    )
    assert r.status_code == 409 and r.json()["error"]["type"] == "already_member"  # AC10


async def test_cross_project_isolation_404(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, a_h = await _auth(db_session)
    _, b_h = await _auth(db_session)
    pid_a = await _project(async_client, a_h)
    # B is a complete stranger to project A -> 404 (existence not leaked).
    assert (await async_client.get(f"{PROJECTS}/{pid_a}/members", headers=b_h)).status_code == 404
    assert (
        await async_client.get(f"{PROJECTS}/{pid_a}/invites", headers=b_h)
    ).status_code == 404
