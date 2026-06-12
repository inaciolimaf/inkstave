"""Integration tests for the file-tree API — move operations (spec 12)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration._tree_api_support import _auth, _create, _project, _tree

pytestmark = pytest.mark.integration


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


async def test_move_to_cross_project_parent_is_404(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Spec 12 §8: "Move: cross-project target → 404." Moving an entity onto a parent
    # that belongs to a *different* project must be rejected as parent_not_found.
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    other_pid = await _project(async_client, headers)
    doc = await _create(async_client, pid, headers, type_="doc", name="m.tex")
    other_folder = await _create(async_client, other_pid, headers, type_="folder", name="dest")

    resp = await async_client.patch(
        f"{_tree(pid)}/entities/{doc['json']['id']}/move",  # type: ignore[index]
        json={"new_parent_id": other_folder["json"]["id"]},  # type: ignore[index]
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "parent_not_found"


async def test_move_name_collision_at_destination_is_409(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Spec 12 §8: "name collision at destination 409." Moving an entity into a folder
    # that already holds a same-named sibling must conflict.
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    dest = await _create(async_client, pid, headers, type_="folder", name="dest")
    # A "dup.tex" already inside the destination folder.
    await _create(
        async_client,
        pid,
        headers,
        type_="doc",
        name="dup.tex",
        parent_id=dest["json"]["id"],  # type: ignore[index]
    )
    # A second "dup.tex" at the root, which we then try to move into the destination.
    moving = await _create(async_client, pid, headers, type_="doc", name="dup.tex")

    resp = await async_client.patch(
        f"{_tree(pid)}/entities/{moving['json']['id']}/move",  # type: ignore[index]
        json={"new_parent_id": dest["json"]["id"]},  # type: ignore[index]
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "name_conflict"
