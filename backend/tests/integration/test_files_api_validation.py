"""Integration tests for the binary file API (spec 14): name & content validation.

Covers upload size limits, MIME/extension sniffing, and the
sanitize-then-validate name policy (traversal, reserved, control chars).
Shared helpers and fixtures live in ``_files_api_support``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.config import get_settings
from inkstave.storage.base import ObjectStore

from ._files_api_support import (
    _auth,
    _project,
    _upload,
    client_store,
    object_store,
)

pytestmark = pytest.mark.integration

__all__ = ["client_store", "object_store"]


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
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    # Deliberate spec-52 §5.2.5 sanitize-then-validate policy, superseding spec-14 AC5
    # (which asked for a hard 422 invalid_name). A traversal name is *sanitized*
    # ("../evil" → "evil") rather than rejected as invalid; with no allowed extension
    # left, the sanitized name is rejected 415 and nothing is ever written to storage.
    resp = await _upload(client, pid, headers, name="../evil")
    assert resp.status_code == 415
    assert resp.json()["error"]["type"] == "unsupported_media_type"
    # Nothing left behind: no tree entity and no blob under the project's storage area.
    tree = (await client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    assert tree["root"]["children"] == []
    assert not await store.exists(f"projects/{pid}/files/evil")


async def test_upload_content_extension_mismatch_is_415(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    # spec 52 §5.2.5: a .png whose bytes are really a PDF is rejected.
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(
        client, pid, headers, filename="fake.png", content=b"%PDF-1.7 not a png",
        content_type="image/png", name="fake.png",
    )
    assert resp.status_code == 415


async def test_upload_traversal_filename_is_sanitized_and_stored_safely(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    # spec 52 §5.2.5 / AC7: a traversal name with a valid extension is sanitized and
    # stored under its safe basename — never outside the project's storage area.
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(client, pid, headers, name="../../etc/logo.png")
    assert resp.status_code == 201
    assert resp.json()["name"] == "logo.png"


async def test_upload_reserved_name_is_rejected(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    # AC5 (spec 15): the upload path rejects Windows-reserved device names. After
    # sanitization ``con.png`` still has the reserved stem ``con``, so
    # ``validate_name_segment`` rejects it with 422 invalid_name — nothing is stored.
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(client, pid, headers, name="con.png")
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "invalid_name"
    tree = (await client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    assert tree["root"]["children"] == []
    assert not await store.exists(f"projects/{pid}/files/con.png")


async def test_upload_control_char_name_is_sanitized_safely(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    # AC5 (spec 15): the upload path neutralises control characters. A NUL byte in
    # the name is stripped by ``sanitize_filename`` ("with\x00nul.png" → "withnul.png");
    # the remaining ``.png`` is valid and matches the PNG bytes, so it is accepted and
    # stored under the sanitized basename — no raw control character ever reaches the
    # stored name or storage key. (Rename-path reserved/control coverage lives in
    # test_tree_api.py, which is out of scope for this pack; the upload path is here.)
    client, store = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    resp = await _upload(client, pid, headers, name="with\x00nul.png")
    assert resp.status_code == 201
    eid = resp.json()["entity_id"]
    stored_name = resp.json()["name"]
    assert "\x00" not in stored_name
    assert stored_name == "withnul.png"
    assert await store.exists(f"projects/{pid}/files/{eid}")
