"""Integration tests for the file-tree API — create, list & rename (spec 12)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration._tree_api_support import _auth, _create, _project, _tree

pytestmark = pytest.mark.integration


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
