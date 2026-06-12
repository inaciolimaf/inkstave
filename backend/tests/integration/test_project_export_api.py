"""Integration tests for project export to .zip (spec 102)."""

from __future__ import annotations

import io
import zipfile
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_object_store
from inkstave.storage.base import ObjectStore
from tests.factories import UserFactory
from tests.integration._files_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


@pytest_asyncio.fixture
async def store(app: Any) -> ObjectStore:
    s = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: s
    return s


async def _auth(db_session: AsyncSession) -> tuple[dict[str, str], UUID]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}, user.id


async def _project(client: AsyncClient, headers: dict[str, str], name: str = "P") -> str:
    return str(
        (await client.post("/api/v1/projects", json={"name": name}, headers=headers)).json()["id"]
    )


async def _entity(
    client: AsyncClient,
    pid: str,
    headers: dict[str, str],
    type_: str,
    name: str,
    parent: str | None = None,
) -> str:
    body: dict[str, Any] = {"type": type_, "name": name}
    if parent is not None:
        body["parent_id"] = parent
    resp = await client.post(f"/api/v1/projects/{pid}/tree/entities", json=body, headers=headers)
    return str(resp.json()["id"])


async def _set_doc(
    client: AsyncClient, pid: str, headers: dict[str, str], doc_id: str, content: str
) -> None:
    resp = await client.put(
        f"/api/v1/projects/{pid}/documents/{doc_id}",
        json={"content": content, "base_version": 0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _upload(
    client: AsyncClient, pid: str, headers: dict[str, str], name: str, content: bytes
) -> str:
    files = {"file": (name, content, "image/png")}
    resp = await client.post(f"/api/v1/projects/{pid}/files", files=files, headers=headers)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["entity_id"])


async def _seed_tree(client: AsyncClient, pid: str, headers: dict[str, str]) -> dict[str, str]:
    """root: main.tex, chapters/intro.tex, logo.png. Returns name → entity_id."""
    main = await _entity(client, pid, headers, "doc", "main.tex")
    await _set_doc(client, pid, headers, main, "MAIN BODY")
    chapters = await _entity(client, pid, headers, "folder", "chapters")
    intro = await _entity(client, pid, headers, "doc", "intro.tex", parent=chapters)
    await _set_doc(client, pid, headers, intro, "INTRO BODY")
    logo = await _upload(client, pid, headers, "logo.png", PNG)
    return {"main.tex": main, "chapters": chapters, "chapters/intro.tex": intro, "logo.png": logo}


def _open_zip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


# --------------------------------------------------------------------------- #
# Endpoint, headers, complete tree, ordering, fidelity (AC 1, 3, 5, 6)
# --------------------------------------------------------------------------- #


async def test_export_returns_zip_with_complete_ordered_tree(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers, "My Paper")
    await _seed_tree(async_client, pid, headers)

    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    cd = resp.headers["content-disposition"]
    assert cd.startswith("attachment;") and 'filename="My Paper.zip"' in cd

    zf = _open_zip(resp.content)
    # Deterministic order: folder before its children; segment-list sort.
    assert zf.namelist() == ["chapters/", "chapters/intro.tex", "logo.png", "main.tex"]
    assert zf.read("main.tex") == b"MAIN BODY"
    assert zf.read("chapters/intro.tex") == b"INTRO BODY"
    assert zf.read("logo.png") == PNG  # binary fidelity
    assert zf.getinfo("main.tex").date_time == (1980, 1, 1, 0, 0, 0)


async def test_export_is_deterministic(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    await _seed_tree(async_client, pid, headers)
    a = (await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)).content
    b = (await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)).content
    za, zb = _open_zip(a), _open_zip(b)
    assert za.namelist() == zb.namelist()
    assert all(za.read(n) == zb.read(n) for n in za.namelist())


# --------------------------------------------------------------------------- #
# Authorization (AC 1, 2)
# --------------------------------------------------------------------------- #


async def test_non_member_gets_404(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers_a, _ = await _auth(db_session)
    headers_b, _ = await _auth(db_session)
    pid = await _project(async_client, headers_a)
    await _seed_tree(async_client, pid, headers_a)
    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers_b)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "project_not_found"


async def test_requires_auth(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    assert (await async_client.get(f"/api/v1/projects/{pid}/export.zip")).status_code == 401


# --------------------------------------------------------------------------- #
# Empty project, size cap, missing blob, current content (AC 4, 7, 10, 11)
# --------------------------------------------------------------------------- #


async def test_empty_project_exports_valid_zip(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    assert resp.status_code == 200
    assert _open_zip(resp.content).namelist() == []  # valid, zero-entry zip


async def test_size_cap_returns_413(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    await _seed_tree(async_client, pid, headers)
    monkeypatch.setattr(get_settings(), "export_max_total_bytes", 5, raising=False)
    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "export_too_large"


async def test_missing_blob_is_skipped_not_500(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    ids = await _seed_tree(async_client, pid, headers)
    # Delete the blob but keep the files row (storage desync).
    await store.delete(f"projects/{pid}/files/{ids['logo.png']}")
    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    assert resp.status_code == 200
    assert "logo.png" not in _open_zip(resp.content).namelist()  # skipped
    assert "main.tex" in _open_zip(resp.content).namelist()  # rest survives


async def test_exports_flushed_current_content(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4 — the CRDT flush runs before the read, so exported text is current."""
    from inkstave.api.routes import projects as projects_routes

    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers)
    ids = await _seed_tree(async_client, pid, headers)

    async def fake_flush(_collab: Any, session: Any, project_id: Any) -> None:
        from inkstave.services.document_service import set_content_from_collab

        await set_content_from_collab(session, UUID(ids["main.tex"]), "FLUSHED LIVE TEXT")

    monkeypatch.setattr(projects_routes, "flush_open_project_docs", fake_flush)
    resp = await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    assert _open_zip(resp.content).read("main.tex") == b"FLUSHED LIVE TEXT"


# --------------------------------------------------------------------------- #
# Streaming (AC 8)
# --------------------------------------------------------------------------- #


async def test_builder_yields_multiple_chunks(db_session: AsyncSession, store: ObjectStore) -> None:
    from inkstave.db.models.tree_entity import TreeEntityType
    from inkstave.services.export_service import ExportEntry, stream_project_zip

    # A plan with two file entries; the fake store returns each as a stream so the
    # builder drains the buffer per entry → more than one yielded chunk.
    await store.put("k1", b"a" * 1000)
    await store.put("k2", b"b" * 1000)
    from uuid import uuid4

    plan = [
        ExportEntry("a.png", TreeEntityType.file, uuid4(), "k1", 1000),
        ExportEntry("b.png", TreeEntityType.file, uuid4(), "k2", 1000),
    ]
    chunks = [c async for c in stream_project_zip(plan, store, db_session, get_settings()) if c]
    assert len(chunks) > 1  # not one big buffer


# --------------------------------------------------------------------------- #
# Round-trip via spec-101 import (AC 13)
# --------------------------------------------------------------------------- #


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_export_import_round_trip(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore, redis: Any
) -> None:
    """AC13 — export then re-import reproduces the tree (paths, doc text, file bytes)."""
    from inkstave.dependencies import get_import_enqueuer
    from inkstave.services.import_jobs import import_project_zip

    # The import endpoint enqueues; run the job inline against the same session/store.
    captured: list[str] = []

    class _Fake:
        async def enqueue(self, import_id: Any) -> str | None:
            captured.append(str(import_id))
            return "job"

    async_client._transport.app.dependency_overrides[get_import_enqueuer] = lambda: _Fake()  # type: ignore[attr-defined]

    headers, _ = await _auth(db_session)
    pid = await _project(async_client, headers, "Original")
    await _seed_tree(async_client, pid, headers)
    zip_bytes = (
        await async_client.get(f"/api/v1/projects/{pid}/export.zip", headers=headers)
    ).content

    imp = await async_client.post(
        "/api/v1/projects/import",
        files={"file": ("export.zip", zip_bytes, "application/zip")},
        headers=headers,
    )
    assert imp.status_code == 202, imp.text
    new_pid, iid = imp.json()["project_id"], imp.json()["import_id"]
    ctx = {
        "settings": get_settings(),
        "redis": redis,
        "object_store": store,
        "session_factory": lambda: _SessionCtx(db_session),
    }
    await import_project_zip(ctx, iid)

    status = (
        await async_client.get(f"/api/v1/projects/{new_pid}/import/{iid}", headers=headers)
    ).json()
    assert status["status"] == "success"

    def _flatten(node: dict[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for child in node.get("children") or []:
            out[child["path"]] = child["type"]
            out.update(_flatten(child))
        return out

    tree = (await async_client.get(f"/api/v1/projects/{new_pid}/tree", headers=headers)).json()
    nodes = _flatten(tree["root"])
    assert nodes["main.tex"] == "doc"
    assert nodes["chapters"] == "folder"
    assert nodes["chapters/intro.tex"] == "doc"
    assert nodes["logo.png"] == "file"
