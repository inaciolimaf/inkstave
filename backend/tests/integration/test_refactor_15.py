"""Spec 15 refactor: perf-sanity (no N+1), unique-race 409, ownership parity."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_object_store
from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore, PutData
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


class _InMemoryStore(ObjectStore):
    """Minimal in-memory object store (no filesystem/network) for upload-backed tests."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[bytes, str | None]] = {}

    async def put(self, key: str, data: PutData, *, content_type: str | None = None) -> ObjectStat:
        body = data if isinstance(data, bytes) else b"".join([c async for c in data])
        self._d[key] = (body, content_type)
        return ObjectStat(size=len(body), content_type=content_type)

    async def stat(self, key: str) -> ObjectStat:
        if key not in self._d:
            raise ObjectNotFoundError(key)
        body, ct = self._d[key]
        return ObjectStat(size=len(body), content_type=ct)

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._d

    async def open(self, key: str) -> tuple[ObjectStat, AsyncIterator[bytes]]:
        if key not in self._d:
            raise ObjectNotFoundError(key)
        body, ct = self._d[key]

        async def stream() -> AsyncIterator[bytes]:
            yield body

        return ObjectStat(size=len(body), content_type=ct), stream()


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project(client: AsyncClient, headers: dict[str, str]) -> str:
    return str(
        (await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"]
    )


async def _create_entity(
    client: AsyncClient, pid: str, headers: dict[str, str], type_: str, name: str
) -> str:
    resp = await client.post(
        f"/api/v1/projects/{pid}/tree/entities", json={"type": type_, "name": name}, headers=headers
    )
    return str(resp.json()["id"])


# --- No N+1 on hot paths (AC3) --------------------------------------------- #


async def test_tree_list_issues_constant_queries(
    async_client: AsyncClient, db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    for i in range(10):
        await _create_entity(async_client, pid, headers, "doc", f"d{i}.tex")

    query_counter["count"] = 0
    resp = await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["root"]["children"]) == 10
    # Whole tree comes from a single query — count does not scale with node count.
    assert query_counter["count"] <= 4


async def test_project_list_does_not_lazy_load_owner(
    async_client: AsyncClient, db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    headers = await _auth(db_session)
    for i in range(5):
        await async_client.post("/api/v1/projects", json={"name": f"P{i}"}, headers=headers)

    query_counter["count"] = 0
    resp = await async_client.get("/api/v1/projects", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 5
    # count + select, no per-row owner load (would be 5 extra otherwise).
    assert query_counter["count"] <= 4


async def test_document_get_is_few_queries(
    async_client: AsyncClient, db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _create_entity(async_client, pid, headers, "doc", "main.tex")

    query_counter["count"] = 0
    resp = await async_client.get(f"/api/v1/projects/{pid}/documents/{eid}", headers=headers)
    assert resp.status_code == 200
    assert query_counter["count"] <= 5


async def test_file_get_is_few_queries(
    app: Any, async_client: AsyncClient, db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    # Inject an in-memory object store so the upload needs no real filesystem/network.
    app.dependency_overrides[get_object_store] = lambda: _InMemoryStore()
    try:
        headers = await _auth(db_session)
        pid = await _project(async_client, headers)
        files = {"file": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "image/png")}
        upload = await async_client.post(
            f"/api/v1/projects/{pid}/files", files=files, headers=headers
        )
        assert upload.status_code == 201
        eid = upload.json()["entity_id"]

        query_counter["count"] = 0
        resp = await async_client.get(f"/api/v1/projects/{pid}/files/{eid}", headers=headers)
        assert resp.status_code == 200
        # Metadata + name come from a bounded set of queries; count does not scale (no N+1).
        assert query_counter["count"] <= 5
    finally:
        app.dependency_overrides.pop(get_object_store, None)


# --- Unique-constraint race maps to 409, not 500 (AC6) --------------------- #


async def test_create_name_race_maps_to_409(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    await _create_entity(async_client, pid, headers, "doc", "race.tex")

    # Force the pre-check to miss so the INSERT races into the unique index.
    import inkstave.services.tree_service as tree_service

    async def _never(*_a: Any, **_k: Any) -> bool:
        return False

    monkeypatch.setattr(tree_service, "_sibling_exists", _never)
    resp = await async_client.post(
        f"/api/v1/projects/{pid}/tree/entities",
        json={"type": "doc", "name": "race.tex"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "name_conflict"


async def test_rename_name_race_maps_to_409(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    await _create_entity(async_client, pid, headers, "doc", "taken.tex")
    other = await _create_entity(async_client, pid, headers, "doc", "other.tex")

    import inkstave.services.tree_service as tree_service

    async def _never(*_a: Any, **_k: Any) -> bool:
        return False

    monkeypatch.setattr(tree_service, "_sibling_exists", _never)
    resp = await async_client.patch(
        f"/api/v1/projects/{pid}/tree/entities/{other}/rename",
        json={"name": "taken.tex"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "name_conflict"


async def test_move_name_race_maps_to_409(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    folder = await _create_entity(async_client, pid, headers, "folder", "F")
    moving = await _create_entity(async_client, pid, headers, "doc", "dup.tex")  # under root
    # A sibling with the same name already exists under the destination folder.
    await async_client.post(
        f"/api/v1/projects/{pid}/tree/entities",
        json={"type": "doc", "name": "dup.tex", "parent_id": folder},
        headers=headers,
    )

    import inkstave.services.tree_service as tree_service

    async def _never(*_a: Any, **_k: Any) -> bool:
        return False

    monkeypatch.setattr(tree_service, "_sibling_exists", _never)
    resp = await async_client.patch(
        f"/api/v1/projects/{pid}/tree/entities/{moving}/move",
        json={"new_parent_id": folder},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "name_conflict"


# --- Ownership = existence (404, never 403) across resource types (AC2) ----- #


async def test_ownership_is_404_across_resources(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(async_client, headers_a)
    doc = await _create_entity(async_client, pid, headers_a, "doc", "main.tex")

    targets = [
        f"/api/v1/projects/{pid}",
        f"/api/v1/projects/{pid}/tree",
        f"/api/v1/projects/{pid}/tree/entities/{doc}/rename",  # GET (405) — skip mutation
        f"/api/v1/projects/{pid}/documents/{doc}",
        f"/api/v1/projects/{pid}/files/{doc}",
    ]
    # GETs only (no mutation), asserting 404 project_not_found for the other user.
    for url in (targets[0], targets[1], targets[3], targets[4]):
        resp = await async_client.get(url, headers=headers_b)
        assert resp.status_code == 404, url
        assert resp.json()["error"]["type"] == "project_not_found", url


async def test_get_file_without_content_row_is_404(db_session: AsyncSession) -> None:
    # A `file` entity created without an upload (no `files` row) reports 404.
    from inkstave.db.models.tree_entity import TreeEntityType
    from inkstave.services.file_service import get_file
    from inkstave.services.project import create_project
    from inkstave.services.tree_service import EntityNotFoundError, create_entity, ensure_root

    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    root = await ensure_root(db_session, project.id)
    entity = await create_entity(db_session, project.id, TreeEntityType.file, "x.png", root.id)
    with pytest.raises(EntityNotFoundError):
        await get_file(db_session, project.id, entity.id)
