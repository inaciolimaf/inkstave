"""Integration tests for the project CRUD API (spec 11)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.user import User
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


async def _auth_user(db_session: AsyncSession) -> tuple[User, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


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
    fetched = await async_client.get(f"{PROJECTS}/{project_id}", headers=headers)
    assert fetched.status_code == 200

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
    for call in (
        async_client.get(f"{PROJECTS}/{project_id}", headers=headers),
        async_client.patch(f"{PROJECTS}/{project_id}", json={"name": "x"}, headers=headers),
        async_client.delete(f"{PROJECTS}/{project_id}", headers=headers),
    ):
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"
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
