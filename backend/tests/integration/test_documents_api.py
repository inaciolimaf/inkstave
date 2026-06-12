"""Integration tests for the document content API (spec 13)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.db.models.document import Document
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


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


def _doc_url(pid: str, eid: str) -> str:
    return f"/api/v1/projects/{pid}/documents/{eid}"


async def test_new_doc_has_empty_content(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    resp = await async_client.get(_doc_url(pid, eid), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == ""
    assert body["version"] == 0
    assert body["size_bytes"] == 0


async def test_replace_increments_version(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    content = "\\documentclass{article}"
    resp = await async_client.put(
        _doc_url(pid, eid), json={"content": content, "base_version": 0}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["content"] == content
    assert body["size_bytes"] == len(content.encode())

    fetched = (await async_client.get(_doc_url(pid, eid), headers=headers)).json()
    assert fetched["version"] == 1
    assert fetched["content"] == content


async def test_stale_version_conflicts_with_server_state(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    await async_client.put(
        _doc_url(pid, eid), json={"content": "current", "base_version": 0}, headers=headers
    )
    conflict = await async_client.put(
        _doc_url(pid, eid), json={"content": "stale", "base_version": 0}, headers=headers
    )
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error"]["type"] == "version_conflict"
    assert body["error"]["details"][0]["current_version"] == 1
    assert body["error"]["details"][0]["current_content"] == "current"

    # Document unchanged at version 1.
    fetched = (await async_client.get(_doc_url(pid, eid), headers=headers)).json()
    assert fetched["version"] == 1
    assert fetched["content"] == "current"


async def test_no_lost_update(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    await async_client.put(
        _doc_url(pid, eid), json={"content": "v1", "base_version": 0}, headers=headers
    )

    first = await async_client.put(
        _doc_url(pid, eid), json={"content": "a", "base_version": 1}, headers=headers
    )
    second = await async_client.put(
        _doc_url(pid, eid), json={"content": "b", "base_version": 1}, headers=headers
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]


async def test_content_too_large(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    monkeypatch.setenv("MAX_DOCUMENT_BYTES", "8")
    get_settings.cache_clear()
    resp = await async_client.put(
        _doc_url(pid, eid), json={"content": "way too long", "base_version": 0}, headers=headers
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "content_too_large"


async def test_non_doc_entity_is_conflict(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    folder = await _entity(async_client, pid, headers, "folder", "figs")
    resp = await async_client.get(_doc_url(pid, folder), headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "not_a_document"


async def test_file_entity_is_conflict(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC6: GET and PUT content on a ``file`` entity both return 409 not_a_document.

    The tree-create route only accepts ``folder``/``doc``; ``file`` entities are
    created by the upload service, so we insert one directly to exercise the guard.
    """
    from uuid import UUID as _UUID

    from inkstave.db.models.tree_entity import TreeEntityType
    from inkstave.services.tree_service import create_entity, ensure_root

    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    root = await ensure_root(db_session, _UUID(pid))
    file_entity = await create_entity(
        db_session, _UUID(pid), TreeEntityType.file, "logo.png", root.id
    )
    await db_session.commit()
    file_eid = str(file_entity.id)
    get_resp = await async_client.get(_doc_url(pid, file_eid), headers=headers)
    assert get_resp.status_code == 409
    assert get_resp.json()["error"]["type"] == "not_a_document"
    put_resp = await async_client.put(
        _doc_url(pid, file_eid), json={"content": "x", "base_version": 0}, headers=headers
    )
    assert put_resp.status_code == 409
    assert put_resp.json()["error"]["type"] == "not_a_document"


async def test_base_version_greater_than_current_conflicts(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Spec 13 §5.2: base_version > current version → 409 version_conflict."""
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    resp = await async_client.put(
        _doc_url(pid, eid), json={"content": "future", "base_version": 5}, headers=headers
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["type"] == "version_conflict"
    assert body["error"]["details"][0]["current_version"] == 0
    # Document is untouched at the initial empty version 0.
    fetched = (await async_client.get(_doc_url(pid, eid), headers=headers)).json()
    assert fetched["version"] == 0
    assert fetched["content"] == ""


async def test_missing_entity_is_404(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    resp = await async_client.get(_doc_url(pid, str(uuid4())), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "entity_not_found"


async def test_ownership_isolation(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(async_client, headers_a)
    eid = await _entity(async_client, pid, headers_a, "doc", "main.tex")
    for call in (
        async_client.get(_doc_url(pid, eid), headers=headers_b),
        async_client.put(
            _doc_url(pid, eid), json={"content": "x", "base_version": 0}, headers=headers_b
        ),
    ):
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"


async def test_requires_auth(async_client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    assert (await async_client.get(_doc_url(pid, eid))).status_code == 401


async def test_delete_entity_cascades_content(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    pid = await _project(async_client, headers)
    eid = await _entity(async_client, pid, headers, "doc", "main.tex")
    await async_client.put(
        _doc_url(pid, eid), json={"content": "x", "base_version": 0}, headers=headers
    )

    deleted = await async_client.delete(
        f"/api/v1/projects/{pid}/tree/entities/{eid}", headers=headers
    )
    assert deleted.status_code == 204

    # The content row is gone via the FK cascade.
    rows = (await db_session.execute(select(Document).where(Document.entity_id == eid))).all()
    assert rows == []
    assert (await async_client.get(_doc_url(pid, eid), headers=headers)).status_code == 404
