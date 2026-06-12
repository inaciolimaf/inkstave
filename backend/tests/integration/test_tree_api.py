"""Integration tests for the file-tree API (spec 12)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project(async_client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await async_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    return str(resp.json()["id"])


def _tree(pid: str) -> str:
    return f"/api/v1/projects/{pid}/tree"


async def _create(
    client: AsyncClient,
    pid: str,
    headers: dict[str, str],
    *,
    type_: str = "folder",
    name: str,
    parent_id: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {"type": type_, "name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = await client.post(f"{_tree(pid)}/entities", json=body, headers=headers)
    return {"status": resp.status_code, "json": resp.json() if resp.content else None}


async def test_root_auto_created(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.get(_tree(pid), headers=headers)
    assert resp.status_code == 200
    root = resp.json()["root"]
    assert root["is_root"] is True
    assert root["type"] == "folder"
    assert root["name"] == ""
    assert root["children"] == []


async def test_create_and_paths(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)

    folder = await _create(async_client, pid, headers, type_="folder", name="figures")
    doc = await _create(async_client, pid, headers, type_="doc", name="main.tex")
    assert folder["status"] == 201
    assert doc["status"] == 201
    assert folder["json"]["path"] == "figures"  # type: ignore[index]
    assert doc["json"]["path"] == "main.tex"  # type: ignore[index]

    nested = await _create(
        async_client,
        pid,
        headers,
        type_="doc",
        name="diagram.tex",
        parent_id=folder["json"]["id"],  # type: ignore[index]
    )
    assert nested["json"]["path"] == "figures/diagram.tex"  # type: ignore[index]
    assert nested["json"]["parent_id"] == folder["json"]["id"]  # type: ignore[index]


async def test_duplicate_name_is_case_insensitive_conflict(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    await _create(async_client, pid, headers, type_="doc", name="Main.tex")
    dup = await _create(async_client, pid, headers, type_="doc", name="main.tex")
    assert dup["status"] == 409
    assert dup["json"]["error"]["type"] == "name_conflict"  # type: ignore[index]


@pytest.mark.parametrize("name", ["..", "a/b", "a\\b", "con", "with\x00nul", ""])
async def test_invalid_names_rejected(
    async_client: AsyncClient, db_session: AsyncSession, name: str
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    result = await _create(async_client, pid, headers, type_="doc", name=name)
    assert result["status"] == 422


async def test_create_under_non_folder_parent(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    doc = await _create(async_client, pid, headers, type_="doc", name="parent.tex")
    child = await _create(
        async_client,
        pid,
        headers,
        type_="doc",
        name="child.tex",
        parent_id=doc["json"]["id"],  # type: ignore[index]
    )
    assert child["status"] == 422
    assert child["json"]["error"]["type"] == "parent_not_a_folder"  # type: ignore[index]


async def test_create_under_other_project_parent_is_404(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    other_pid = await _project(async_client, headers)
    other_folder = await _create(async_client, other_pid, headers, type_="folder", name="x")
    child = await _create(
        async_client,
        pid,
        headers,
        type_="doc",
        name="c.tex",
        parent_id=other_folder["json"]["id"],  # type: ignore[index]
    )
    assert child["status"] == 404
    assert child["json"]["error"]["type"] == "parent_not_found"  # type: ignore[index]


async def test_rename(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    a = await _create(async_client, pid, headers, type_="doc", name="a.tex")
    await _create(async_client, pid, headers, type_="doc", name="taken.tex")
    eid = a["json"]["id"]  # type: ignore[index]

    ok = await async_client.patch(
        f"{_tree(pid)}/entities/{eid}/rename", json={"name": "b.tex"}, headers=headers
    )
    assert ok.status_code == 200
    assert ok.json()["name"] == "b.tex"

    conflict = await async_client.patch(
        f"{_tree(pid)}/entities/{eid}/rename", json={"name": "taken.tex"}, headers=headers
    )
    assert conflict.status_code == 409

    invalid = await async_client.patch(
        f"{_tree(pid)}/entities/{eid}/rename", json={"name": ".."}, headers=headers
    )
    assert invalid.status_code == 422


async def test_move_cycle_and_non_folder(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    a = await _create(async_client, pid, headers, type_="folder", name="A")
    b = await _create(
        async_client,
        pid,
        headers,
        type_="folder",
        name="B",
        parent_id=a["json"]["id"],  # type: ignore[index]
    )
    a_id = a["json"]["id"]  # type: ignore[index]
    b_id = b["json"]["id"]  # type: ignore[index]

    # Move A into its descendant B -> cycle.
    cycle = await async_client.patch(
        f"{_tree(pid)}/entities/{a_id}/move", json={"new_parent_id": b_id}, headers=headers
    )
    assert cycle.status_code == 409
    assert cycle.json()["error"]["type"] == "tree_cycle"

    # A's parent is unchanged (still under root).
    tree = (await async_client.get(_tree(pid), headers=headers)).json()
    assert any(c["id"] == a_id for c in tree["root"]["children"])

    # Move a doc under a doc -> parent_not_a_folder.
    d1 = await _create(async_client, pid, headers, type_="doc", name="d1.tex")
    d2 = await _create(async_client, pid, headers, type_="doc", name="d2.tex")
    bad = await async_client.patch(
        f"{_tree(pid)}/entities/{d1['json']['id']}/move",  # type: ignore[index]
        json={"new_parent_id": d2["json"]["id"]},  # type: ignore[index]
        headers=headers,
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["type"] == "parent_not_a_folder"


async def test_move_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    folder = await _create(async_client, pid, headers, type_="folder", name="dest")
    doc = await _create(async_client, pid, headers, type_="doc", name="m.tex")
    moved = await async_client.patch(
        f"{_tree(pid)}/entities/{doc['json']['id']}/move",  # type: ignore[index]
        json={"new_parent_id": folder["json"]["id"]},  # type: ignore[index]
        headers=headers,
    )
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == folder["json"]["id"]  # type: ignore[index]
    assert moved.json()["path"] == "dest/m.tex"


async def test_delete_recursive(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    folder = await _create(async_client, pid, headers, type_="folder", name="sub")
    await _create(
        async_client,
        pid,
        headers,
        type_="doc",
        name="inner.tex",
        parent_id=folder["json"]["id"],  # type: ignore[index]
    )

    deleted = await async_client.delete(
        f"{_tree(pid)}/entities/{folder['json']['id']}",
        headers=headers,  # type: ignore[index]
    )
    assert deleted.status_code == 204

    tree = (await async_client.get(_tree(pid), headers=headers)).json()
    assert tree["root"]["children"] == []  # folder and its descendant are gone


async def test_root_is_immutable(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    root_id = (await async_client.get(_tree(pid), headers=headers)).json()["root"]["id"]
    folder = await _create(async_client, pid, headers, type_="folder", name="f")

    rename = await async_client.patch(
        f"{_tree(pid)}/entities/{root_id}/rename", json={"name": "x"}, headers=headers
    )
    move = await async_client.patch(
        f"{_tree(pid)}/entities/{root_id}/move",
        json={"new_parent_id": folder["json"]["id"]},  # type: ignore[index]
        headers=headers,
    )
    delete = await async_client.delete(f"{_tree(pid)}/entities/{root_id}", headers=headers)
    for resp in (rename, move, delete):
        assert resp.status_code == 409
        assert resp.json()["error"]["type"] == "root_immutable"


async def test_ownership_isolation(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(async_client, headers_a)
    entity = await _create(async_client, pid, headers_a, type_="doc", name="a.tex")
    eid = entity["json"]["id"]  # type: ignore[index]

    calls = [
        async_client.get(_tree(pid), headers=headers_b),
        async_client.post(
            f"{_tree(pid)}/entities", json={"type": "doc", "name": "x"}, headers=headers_b
        ),
        async_client.patch(
            f"{_tree(pid)}/entities/{eid}/rename", json={"name": "y"}, headers=headers_b
        ),
        async_client.delete(f"{_tree(pid)}/entities/{eid}", headers=headers_b),
    ]
    for call in calls:
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"


async def test_tree_requires_auth(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    assert (await async_client.get(_tree(pid))).status_code == 401
    assert (
        await async_client.post(f"{_tree(pid)}/entities", json={"type": "doc", "name": "x"})
    ).status_code == 401


async def test_unknown_entity_is_404(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.delete(f"{_tree(pid)}/entities/{uuid4()}", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "entity_not_found"
