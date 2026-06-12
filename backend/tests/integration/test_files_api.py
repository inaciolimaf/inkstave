"""Integration tests for the binary file API (spec 14).

Parametrised over the ``local`` backend (tmp dir) and an in-memory store that
stands in for an S3-compatible backend, proving the abstraction is
backend-agnostic (AC10) — no network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_object_store
from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore, PutData
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class InMemoryObjectStore(ObjectStore):
    """A faithful in-memory store standing in for an S3-compatible backend."""

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


@pytest.fixture(params=["local", "memory"])
def object_store(request: pytest.FixtureRequest, tmp_path: Any) -> ObjectStore:
    if request.param == "local":
        return LocalObjectStore(tmp_path, 65536)
    return InMemoryObjectStore()


@pytest_asyncio.fixture
async def client_store(
    app: Any, async_client: AsyncClient, object_store: ObjectStore
) -> AsyncIterator[tuple[AsyncClient, ObjectStore]]:
    app.dependency_overrides[get_object_store] = lambda: object_store
    try:
        yield async_client, object_store
    finally:
        app.dependency_overrides.pop(get_object_store, None)


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project(client: AsyncClient, headers: dict[str, str]) -> str:
    return str(
        (await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"]
    )


async def _entity(
    client: AsyncClient, pid: str, headers: dict[str, str], type_: str, name: str
) -> str:
    resp = await client.post(
        f"/api/v1/projects/{pid}/tree/entities",
        json={"type": type_, "name": name},
        headers=headers,
    )
    return str(resp.json()["id"])


async def _upload(
    client: AsyncClient,
    pid: str,
    headers: dict[str, str],
    *,
    filename: str = "logo.png",
    content: bytes = PNG,
    content_type: str = "image/png",
    name: str | None = None,
    parent_id: str | None = None,
) -> Any:
    files = {"file": (filename, content, content_type)}
    data: dict[str, str] = {}
    if name is not None:
        data["name"] = name
    if parent_id is not None:
        data["parent_id"] = parent_id
    return await client.post(
        f"/api/v1/projects/{pid}/files", files=files, data=data, headers=headers
    )


def _files(pid: str) -> str:
    return f"/api/v1/projects/{pid}/files"


async def test_upload_then_download_roundtrip(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)

    resp = await _upload(client, pid, headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(PNG)
    assert len(body["checksum_sha256"]) == 64
    eid = body["entity_id"]

    # Blob exists under the per-project key.
    assert await store.exists(f"projects/{pid}/files/{eid}")
    # A file tree entity appears.
    tree = (await client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    assert any(c["type"] == "file" for c in tree["root"]["children"])

    # Download is byte-for-byte equal with correct headers.
    dl = await client.get(f"{_files(pid)}/{eid}/content", headers=headers)
    assert dl.status_code == 200
    assert dl.content == PNG
    assert dl.headers["content-type"].startswith("image/png")
    assert dl.headers["content-length"] == str(len(PNG))


async def test_size_limit(
    client_store: tuple[AsyncClient, ObjectStore],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4")
    get_settings.cache_clear()
    resp = await _upload(client, pid, headers, content=b"way too big")
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "file_too_large"
    # Nothing left behind in the tree.
    tree = (await client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    assert tree["root"]["children"] == []


async def test_disallowed_mime(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(
        client,
        pid,
        headers,
        filename="evil.exe",
        content=b"MZ\x90\x00",
        content_type="application/x-dosexec",
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["type"] == "unsupported_media_type"


async def test_invalid_name(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(client, pid, headers, name="../evil")
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "invalid_name"


async def test_non_folder_parent(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    doc = await _entity(client, pid, headers, "doc", "main.tex")
    resp = await _upload(client, pid, headers, parent_id=doc)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "parent_not_a_folder"


async def test_duplicate_name(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    assert (await _upload(client, pid, headers, name="a.png")).status_code == 201
    dup = await _upload(client, pid, headers, name="a.png")
    assert dup.status_code == 409
    assert dup.json()["error"]["type"] == "name_conflict"


async def test_delete_removes_entity_and_blob(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    eid = (await _upload(client, pid, headers)).json()["entity_id"]
    key = f"projects/{pid}/files/{eid}"
    assert await store.exists(key)

    deleted = await client.delete(f"{_files(pid)}/{eid}", headers=headers)
    assert deleted.status_code == 204
    assert await store.exists(key) is False
    assert (await client.get(f"{_files(pid)}/{eid}", headers=headers)).status_code == 404


async def test_blob_missing_download(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    eid = (await _upload(client, pid, headers)).json()["entity_id"]
    await store.delete(f"projects/{pid}/files/{eid}")  # remove blob out-of-band

    resp = await client.get(f"{_files(pid)}/{eid}/content", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "file_blob_missing"


async def test_get_on_non_file_entity(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    folder = await _entity(client, pid, headers, "folder", "figs")
    resp = await client.get(f"{_files(pid)}/{folder}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "not_a_file"


async def test_ownership_isolation(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(client, headers_a)
    eid = (await _upload(client, pid, headers_a)).json()["entity_id"]
    for call in (
        client.get(f"{_files(pid)}/{eid}", headers=headers_b),
        client.get(f"{_files(pid)}/{eid}/content", headers=headers_b),
        client.delete(f"{_files(pid)}/{eid}", headers=headers_b),
    ):
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"


async def test_requires_auth(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    eid = (await _upload(client, pid, headers)).json()["entity_id"]
    assert (await client.get(f"{_files(pid)}/{eid}")).status_code == 401
