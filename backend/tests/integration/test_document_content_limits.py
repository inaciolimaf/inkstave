"""Document content: stored byte-for-byte, and sized by MAX_DOCUMENT_BYTES, not the JSON body cap (spec 13)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _doc(async_client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    project = await async_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    pid = str(project.json()["id"])
    entity = await async_client.post(
        f"/api/v1/projects/{pid}/tree/entities",
        json={"type": "doc", "name": f"{uuid4().hex}.tex"},
        headers=headers,
    )
    return pid, str(entity.json()["id"])


async def test_content_is_stored_byte_for_byte(async_client: AsyncClient, db_session: AsyncSession) -> None:
    # Leading blank lines, indentation and a trailing newline are part of a LaTeX document.
    headers = await _auth(db_session)
    pid, eid = await _doc(async_client, headers)
    url = f"/api/v1/projects/{pid}/documents/{eid}"
    content = "\n\n  \\documentclass{article}\n\\begin{document}\n\t\n"
    resp = await async_client.put(url, json={"content": content, "base_version": 0}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["content"] == content
    assert resp.json()["size_bytes"] == len(content.encode())
    fetched = (await async_client.get(url, headers=headers)).json()
    assert fetched["content"] == content


async def test_document_at_the_size_limit_is_accepted(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # MAX_DOCUMENT_BYTES (2 MB) is the effective limit. LaTeX escapes to about twice its size in
    # JSON, far above the 1 MiB JSON body cap: the body cap must not reject what the size rule allows.
    headers = await _auth(db_session)
    pid, eid = await _doc(async_client, headers)
    content = "\\\n" * 1_000_000  # 2,000,000 bytes
    assert len(content.encode()) == get_settings().max_document_bytes
    resp = await async_client.put(
        f"/api/v1/projects/{pid}/documents/{eid}",
        json={"content": content, "base_version": 0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["size_bytes"] == 2_000_000


async def test_document_over_the_size_limit_is_content_too_large(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Past the document limit the answer is the document rule's 413, not the transport's.
    headers = await _auth(db_session)
    pid, eid = await _doc(async_client, headers)
    content = "x" * (get_settings().max_document_bytes + 1)
    resp = await async_client.put(
        f"/api/v1/projects/{pid}/documents/{eid}",
        json={"content": content, "base_version": 0},
        headers=headers,
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["type"] == "content_too_large"
