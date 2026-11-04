"""Integration tests for share-link takeback and role rules (spec 116).

Turning a link off, or rotating it, takes back exactly what that link granted. A link never lowers
a role. Members whose role the owner set by hand, or who came by e-mail invite, keep their role.
"""

from __future__ import annotations

from typing import Any

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

SHARE_LINKS = "/api/v1/share-links"


async def _link(client: AsyncClient, headers: dict[str, str], pid: str, role: str) -> dict[str, Any]:
    r = await client.post(f"{PROJECTS}/{pid}/share-links", json={"role": role}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _join(client: AsyncClient, headers: dict[str, str], token: str) -> dict[str, Any]:
    r = await client.post(f"{SHARE_LINKS}/{token}/join", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _member(
    client: AsyncClient, owner_h: dict[str, str], pid: str, email: str
) -> dict[str, Any] | None:
    rows = (await client.get(f"{PROJECTS}/{pid}/members", headers=owner_h)).json()
    return next((m for m in rows if m["email"] == email), None)


async def _revoke(client: AsyncClient, owner_h: dict[str, str], pid: str, link: dict[str, Any]) -> None:
    r = await client.delete(f"{PROJECTS}/{pid}/share-links/{link['id']}", headers=owner_h)
    assert r.status_code == 204, r.text


async def test_revoke_restores_previous_role(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, carol_h = await _add_member(async_client, db_session, owner_h, pid, "carol@example.com", role="viewer")
    edit = await _link(async_client, owner_h, pid, "editor")

    # AC3: C was invited as viewer, opens the edit link, becomes editor.
    assert await _join(async_client, carol_h, edit["token"]) == {"project_id": pid, "role": "editor"}
    assert (await _member(async_client, owner_h, pid, "carol@example.com"))["role"] == "editor"

    await _revoke(async_client, owner_h, pid, edit)

    # C is returned to viewer, not removed.
    carol = await _member(async_client, owner_h, pid, "carol@example.com")
    assert carol is not None
    assert carol["role"] == "viewer"
    assert carol["via_link"] is False


async def test_revoke_removes_link_only_members(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    view = await _link(async_client, owner_h, pid, "viewer")
    _, dan_h = await _auth(db_session, email="dan@example.com")
    await _join(async_client, dan_h, view["token"])
    assert (await _member(async_client, owner_h, pid, "dan@example.com"))["via_link"] is True

    await _revoke(async_client, owner_h, pid, view)

    assert await _member(async_client, owner_h, pid, "dan@example.com") is None
    assert (await async_client.get(f"{PROJECTS}/{pid}/permissions", headers=dan_h)).status_code == 404


async def test_view_link_does_not_downgrade_editor(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", role="editor")
    view = await _link(async_client, owner_h, pid, "viewer")

    assert await _join(async_client, bob_h, view["token"]) == {"project_id": pid, "role": "editor"}

    bob = await _member(async_client, owner_h, pid, "bob@example.com")
    assert bob["role"] == "editor"
    assert bob["via_link"] is False  # nothing changed, so nothing is attributed to the link

    await _revoke(async_client, owner_h, pid, view)
    assert (await _member(async_client, owner_h, pid, "bob@example.com"))["role"] == "editor"


async def test_hand_set_role_is_not_taken_back(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, carol_h = await _add_member(async_client, db_session, owner_h, pid, "carol@example.com", role="viewer")
    edit = await _link(async_client, owner_h, pid, "editor")
    await _join(async_client, carol_h, edit["token"])
    carol_id = (await _member(async_client, owner_h, pid, "carol@example.com"))["user_id"]

    # The owner sets the role by hand: the access no longer depends on the link.
    r = await async_client.patch(
        f"{PROJECTS}/{pid}/members/{carol_id}", json={"role": "editor"}, headers=owner_h
    )
    assert r.status_code == 200
    assert (await _member(async_client, owner_h, pid, "carol@example.com"))["via_link"] is False

    await _revoke(async_client, owner_h, pid, edit)
    assert (await _member(async_client, owner_h, pid, "carol@example.com"))["role"] == "editor"


async def test_email_invited_member_is_not_removed_by_revoke(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _, carol_h = await _add_member(async_client, db_session, owner_h, pid, "carol@example.com", role="viewer")
    view = await _link(async_client, owner_h, pid, "viewer")

    # Already a viewer by invite: joining the view link changes nothing and is not attributed to it.
    await _join(async_client, carol_h, view["token"])
    await _revoke(async_client, owner_h, pid, view)

    carol = await _member(async_client, owner_h, pid, "carol@example.com")
    assert carol is not None and carol["role"] == "viewer"


async def test_rotate_takes_back_only_the_rotated_role(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    view = await _link(async_client, owner_h, pid, "viewer")
    edit = await _link(async_client, owner_h, pid, "editor")
    _, eve_h = await _auth(db_session, email="eve@example.com")
    await _join(async_client, eve_h, view["token"])

    await _link(async_client, owner_h, pid, "editor")  # rotate the edit link only

    eve = await _member(async_client, owner_h, pid, "eve@example.com")
    assert eve is not None and eve["role"] == "viewer"
    assert edit["id"] not in {
        row["id"] for row in (await async_client.get(f"{PROJECTS}/{pid}/share-links", headers=owner_h)).json()
    }
