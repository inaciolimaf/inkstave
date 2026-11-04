"""Integration tests for the per-member "Suggesting" preference (spec 119): the route and /permissions."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration._sharing_api_support import _add_member, _auth, _project

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


async def test_permissions_default_suggest_mode_off(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    res = await async_client.get(f"{PROJECTS}/{pid}/permissions", headers=owner_h)
    assert res.status_code == 200
    assert res.json()["suggest_mode"] is False


async def test_editor_switches_own_suggest_mode(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _editor, editor_h = await _add_member(async_client, db_session, owner_h, pid, "ed@example.com", "editor")

    on = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": True}, headers=editor_h)
    assert on.status_code == 200
    assert on.json() == {"suggest_mode": True}

    perms = await async_client.get(f"{PROJECTS}/{pid}/permissions", headers=editor_h)
    assert perms.json()["suggest_mode"] is True

    # The switch is the caller's own: the owner's preference is untouched.
    owner_perms = await async_client.get(f"{PROJECTS}/{pid}/permissions", headers=owner_h)
    assert owner_perms.json()["suggest_mode"] is False

    off = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": False}, headers=editor_h)
    assert off.json() == {"suggest_mode": False}


async def test_owner_may_suggest(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    res = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": True}, headers=owner_h)
    assert res.status_code == 200
    assert res.json() == {"suggest_mode": True}


async def test_viewer_cannot_switch_suggest_mode(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _viewer, viewer_h = await _add_member(async_client, db_session, owner_h, pid, "vi@example.com", "viewer")
    res = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": True}, headers=viewer_h)
    assert res.status_code == 403
    assert res.json()["error"]["type"] == "insufficient_role"


async def test_non_member_gets_not_found(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    _stranger, stranger_h = await _auth(db_session, "stranger@example.com")
    res = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": True}, headers=stranger_h)
    assert res.status_code == 404


async def test_suggest_mode_rejects_non_boolean(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h)
    res = await async_client.patch(f"{PROJECTS}/{pid}/me", json={"suggest_mode": "maybe"}, headers=owner_h)
    assert res.status_code == 422
