"""Integration tests for the binary file API (spec 14): upload/download lifecycle.

Shared helpers, fixtures and the in-memory store live in ``_files_api_support``.
Sibling modules (``test_files_api_validation`` and ``test_files_api_access``)
cover name/content validation and permission/conflict concerns respectively.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.storage.base import ObjectStore

from ._files_api_support import (
    PNG,
    _auth,
    _files,
    _project,
    _upload,
    client_store,
    object_store,
)

pytestmark = pytest.mark.integration

__all__ = ["client_store", "object_store"]


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
