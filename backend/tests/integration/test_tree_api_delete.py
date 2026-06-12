"""Integration tests for the file-tree API — delete, immutability & permissions (spec 12)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.dependencies import get_object_store
from tests.integration._tree_api_support import (
    InMemoryObjectStore,
    _auth,
    _create,
    _project,
    _tree,
)

pytestmark = pytest.mark.integration


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


async def test_delete_via_tree_api_removes_blob(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Spec 14 §9 DoD: deleting a `file` entity via the tree-API DELETE path must remove
    # its blob (no orphan). Upload a blob, delete the entity through the tree route, and
    # assert the storage key is gone.
    store = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: store
    try:
        headers = await _auth(db_session)
        pid = await _project(async_client, headers)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
        upload = await async_client.post(
            f"/api/v1/projects/{pid}/files",
            files={"file": ("logo.png", png, "image/png")},
            headers=headers,
        )
        assert upload.status_code == 201
        eid = upload.json()["entity_id"]
        key = f"projects/{pid}/files/{eid}"
        assert await store.exists(key)

        deleted = await async_client.delete(f"{_tree(pid)}/entities/{eid}", headers=headers)
        assert deleted.status_code == 204
        assert await store.exists(key) is False
    finally:
        app.dependency_overrides.pop(get_object_store, None)


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
        async_client.patch(
            f"{_tree(pid)}/entities/{eid}/move",
            json={"new_parent_id": str(uuid4())},
            headers=headers_b,
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
