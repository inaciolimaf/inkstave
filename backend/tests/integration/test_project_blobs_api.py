"""Project and file blobs leave object storage when their owner is deleted (spec 14, spec 11).

The blob is removed after the database commit, through a background task. A storage failure is
logged and never turns the delete into an error: the row is already gone.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.infra.deps import get_object_store
from inkstave.modules.auth.credentials.tokens import build_token_service
from tests.factories import UserFactory
from tests.integration._files_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class _BrokenDeleteStore(InMemoryObjectStore):
    async def delete(self, key: str) -> None:
        raise OSError("object storage is unreachable")


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project_with_file(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    pid = str((await client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"])
    upload = await client.post(
        f"/api/v1/projects/{pid}/files",
        files={"file": ("logo.png", PNG, "image/png")},
        headers=headers,
    )
    assert upload.status_code == 201
    eid = str(upload.json()["entity_id"])
    return pid, eid, f"projects/{pid}/files/{eid}"


async def wait_until_gone(store: InMemoryObjectStore, key: str) -> None:
    """Blob deletes run in the background after the commit: poll with a deadline, never sleep blind."""
    for _ in range(500):
        if not await store.exists(key):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"blob {key} was not deleted after the commit")


@pytest.fixture
def store(app: Any) -> InMemoryObjectStore:
    fake = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_object_store, None)


async def test_deleting_a_project_removes_its_file_blobs(
    async_client: AsyncClient, db_session: AsyncSession, store: InMemoryObjectStore
) -> None:
    headers = await _auth(db_session)
    pid, _eid, key = await _project_with_file(async_client, headers)
    assert await store.exists(key)

    deleted = await async_client.delete(f"/api/v1/projects/{pid}", headers=headers)
    assert deleted.status_code == 204
    await wait_until_gone(store, key)


async def test_failing_blob_delete_does_not_fail_the_project_delete(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    broken = _BrokenDeleteStore()
    app.dependency_overrides[get_object_store] = lambda: broken
    try:
        pid, _eid, _key = await _project_with_file(async_client, headers)
        deleted = await async_client.delete(f"/api/v1/projects/{pid}", headers=headers)
        assert deleted.status_code == 204
        gone = await async_client.get(f"/api/v1/projects/{pid}", headers=headers)
        assert gone.status_code == 404
    finally:
        app.dependency_overrides.pop(get_object_store, None)


async def test_failing_blob_delete_does_not_fail_the_file_delete(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _auth(db_session)
    broken = _BrokenDeleteStore()
    app.dependency_overrides[get_object_store] = lambda: broken
    try:
        pid, eid, _key = await _project_with_file(async_client, headers)
        deleted = await async_client.delete(f"/api/v1/projects/{pid}/tree/entities/{eid}", headers=headers)
        assert deleted.status_code == 204
    finally:
        app.dependency_overrides.pop(get_object_store, None)
