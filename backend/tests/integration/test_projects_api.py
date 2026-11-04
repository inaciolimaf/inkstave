"""Integration tests for the project CRUD API (spec 11)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User
from tests.factories import UserFactory

from ._sharing_api_support import FakeInviteEnqueuer, _add_member, _auth, _project, enqueuer

__all__ = ["enqueuer"]

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


async def _auth_user(db_session: AsyncSession) -> tuple[User, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _assert_gone(async_client: AsyncClient, project_id: str, headers: dict[str, str]) -> None:
    """Every route on a deleted project answers 404 project_not_found."""
    for call in (
        async_client.get(f"{PROJECTS}/{project_id}", headers=headers),
        async_client.patch(f"{PROJECTS}/{project_id}", json={"name": "x"}, headers=headers),
        async_client.delete(f"{PROJECTS}/{project_id}", headers=headers),
    ):
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"


async def test_crud_happy_path(async_client: AsyncClient, db_session: AsyncSession) -> None:
    user, headers = await _auth_user(db_session)

    # Create
    created = await async_client.post(PROJECTS, json={"name": "My Paper"}, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["owner_id"] == str(user.id)
    assert body["name"] == "My Paper"
    assert body["root_doc_id"] is None
    assert body["id"] and body["created_at"] and body["updated_at"]
    assert "deleted_at" not in body
    project_id = body["id"]

    # List
    listed = await async_client.get(PROJECTS, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == project_id
    assert "deleted_at" not in listed.json()["items"][0]

    # Get
    assert (await async_client.get(f"{PROJECTS}/{project_id}", headers=headers)).status_code == 200

    # Rename -> updated_at strictly advances
    renamed = await async_client.patch(
        f"{PROJECTS}/{project_id}", json={"name": "  Renamed  "}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"
    assert renamed.json()["updated_at"] > body["updated_at"]

    # Delete -> 204, then gone
    deleted = await async_client.delete(f"{PROJECTS}/{project_id}", headers=headers)
    assert deleted.status_code == 204
    await _assert_gone(async_client, project_id, headers)
    assert (await async_client.get(PROJECTS, headers=headers)).json()["total"] == 0


async def test_ownership_is_existence(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers_a = await _auth_user(db_session)
    _, headers_b = await _auth_user(db_session)

    created = await async_client.post(PROJECTS, json={"name": "A's project"}, headers=headers_a)
    pid = created.json()["id"]

    # B sees nothing and cannot touch A's project — 404, never 403, never the body.
    assert (await async_client.get(PROJECTS, headers=headers_b)).json()["total"] == 0
    for call in (
        async_client.get(f"{PROJECTS}/{pid}", headers=headers_b),
        async_client.patch(f"{PROJECTS}/{pid}", json={"name": "hijack"}, headers=headers_b),
        async_client.delete(f"{PROJECTS}/{pid}", headers=headers_b),
    ):
        resp = await call
        assert resp.status_code == 404
        assert "A's project" not in resp.text
        # AC7: cross-user access is reported as not-found, never authz-leaking.
        assert resp.json()["error"]["type"] == "project_not_found"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", PROJECTS, {"name": "x"}),
        ("get", PROJECTS, None),
        # Fixed ids (not uuid4()) so parametrize collection is deterministic under xdist.
        ("get", f"{PROJECTS}/00000000-0000-0000-0000-0000000000a1", None),
        ("patch", f"{PROJECTS}/00000000-0000-0000-0000-0000000000a2", {"name": "x"}),
        ("delete", f"{PROJECTS}/00000000-0000-0000-0000-0000000000a3", None),
    ],
)
async def test_requires_auth(
    async_client: AsyncClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    resp = await async_client.request(method.upper(), path, json=body)
    assert resp.status_code == 401


async def test_pagination_and_total(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    for i in range(3):
        await async_client.post(PROJECTS, json={"name": f"P{i}"}, headers=headers)

    page1 = await async_client.get(PROJECTS, params={"limit": 2, "offset": 0}, headers=headers)
    assert page1.json()["total"] == 3
    assert len(page1.json()["items"]) == 2

    page2 = await async_client.get(PROJECTS, params={"limit": 2, "offset": 2}, headers=headers)
    assert page2.json()["total"] == 3
    assert len(page2.json()["items"]) == 1


async def test_limit_bounds_enforced(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    resp = await async_client.get(PROJECTS, params={"limit": 200}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


async def test_blank_name_rejected(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    resp = await async_client.post(PROJECTS, json={"name": "   "}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


async def test_bad_uuid_path_param(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    resp = await async_client.get(f"{PROJECTS}/not-a-uuid", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


# --------------------------------------------------------------------------- #
# Shared projects on the dashboard (spec 109)
# --------------------------------------------------------------------------- #


async def _ids(client: AsyncClient, headers: dict[str, str], **params: str) -> list[str]:
    resp = await client.get(PROJECTS, params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["items"]]


async def test_list_includes_shared_projects(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    owner, owner_h = await _auth(db_session, email="owner@example.com")
    pid = await _project(async_client, owner_h, "Shared paper")
    _, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", "editor")

    items = (await async_client.get(PROJECTS, headers=bob_h)).json()["items"]
    assert [i["id"] for i in items] == [pid]
    assert items[0]["role"] == "editor"
    assert items[0]["owner"] == {"id": str(owner.id), "display_name": owner.display_name}
    assert items[0]["owner_id"] == str(owner.id)


async def test_owner_row_carries_owner_role(async_client: AsyncClient, db_session: AsyncSession) -> None:
    owner, owner_h = await _auth(db_session)
    pid = await _project(async_client, owner_h, "Mine")
    items = (await async_client.get(PROJECTS, headers=owner_h)).json()["items"]
    assert [i["id"] for i in items] == [pid]
    assert items[0]["role"] == "owner"
    assert items[0]["owner"]["display_name"] == owner.display_name


async def test_left_member_does_not_see_project(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session, email="owner@example.com")
    pid = await _project(async_client, owner_h, "Paper")
    bob, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", "viewer")
    assert await _ids(async_client, bob_h) == [pid]

    left = await async_client.delete(f"{PROJECTS}/{pid}/members/{bob.id}", headers=bob_h)
    assert left.status_code == 204
    assert await _ids(async_client, bob_h) == []
    assert await _ids(async_client, owner_h) == [pid]


async def test_transfer_keeps_project_for_former_owner(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session, email="owner@example.com")
    pid = await _project(async_client, owner_h, "Handed over")
    bob, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com", "viewer")

    moved = await async_client.post(
        f"{PROJECTS}/{pid}/members/transfer", json={"to_user_id": str(bob.id)}, headers=owner_h
    )
    assert moved.status_code == 200, moved.text

    old = (await async_client.get(PROJECTS, headers=owner_h)).json()["items"]
    assert [(i["id"], i["role"]) for i in old] == [(pid, "editor")]
    new = (await async_client.get(PROJECTS, headers=bob_h)).json()["items"]
    assert [(i["id"], i["role"]) for i in new] == [(pid, "owner")]
    assert new[0]["owner"]["id"] == str(bob.id)


async def test_scopes_partition_all(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session, email="owner@example.com")
    shared_with_bob = await _project(async_client, owner_h, "A2")
    _, bob_h = await _add_member(async_client, db_session, owner_h, shared_with_bob, "bob@example.com")
    own_pid = await _project(async_client, bob_h, "B1")
    await _project(async_client, bob_h, "B2")
    await async_client.delete(f"{PROJECTS}/{own_pid}", headers=bob_h)

    everything = await _ids(async_client, bob_h, scope="all")
    owned = await _ids(async_client, bob_h, scope="owned")
    shared = await _ids(async_client, bob_h, scope="shared")
    assert shared == [shared_with_bob]
    assert len(owned) == 1 and own_pid not in owned
    assert set(owned).isdisjoint(shared)
    assert sorted(owned + shared) == sorted(everything)


async def test_soft_deleted_project_appears_for_nobody(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session, email="owner@example.com")
    pid = await _project(async_client, owner_h, "Doomed")
    _, bob_h = await _add_member(async_client, db_session, owner_h, pid, "bob@example.com")
    assert await _ids(async_client, bob_h) == [pid]

    await async_client.delete(f"{PROJECTS}/{pid}", headers=owner_h)
    assert await _ids(async_client, owner_h) == []
    assert await _ids(async_client, bob_h) == []


async def test_unknown_scope_is_validation_error(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    resp = await async_client.get(PROJECTS, params={"scope": "archived"}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


async def test_offset_past_end_keeps_total(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, headers = await _auth_user(db_session)
    for i in range(3):
        await async_client.post(PROJECTS, json={"name": f"P{i}"}, headers=headers)
    resp = await async_client.get(PROJECTS, params={"offset": 10}, headers=headers)
    assert resp.json() == {"items": [], "total": 3}


async def test_list_projects_single_query(
    async_client: AsyncClient, db_session: AsyncSession, enqueuer: FakeInviteEnqueuer
) -> None:
    _, owner_h = await _auth(db_session, email="owner@example.com")
    for i in range(3):
        await _project(async_client, owner_h, f"P{i}")

    statements: list[str] = []

    def record(conn: object, cursor: object, statement: str, *args: object) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        resp = await async_client.get(PROJECTS, headers=owner_h)
    finally:
        event.remove(Engine, "before_cursor_execute", record)

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 3
    assert len([s for s in statements if "project_memberships" in s]) == 1
