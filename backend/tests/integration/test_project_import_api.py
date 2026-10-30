"""Integration tests for the project-import upload endpoint (spec 101).

The ARQ worker is never used: the endpoint stages the blob and a fake enqueuer records the
call. Only tiny in-memory zips.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.infra.storage.base import ObjectStore
from tests.integration._project_import_support import (
    FakeImportEnqueuer,
    auth,
    install_enqueuer,
    install_store,
    make_zip,
    post_import,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def store(app: Any) -> ObjectStore:
    return install_store(app)


@pytest.fixture
def enqueuer(app: Any) -> FakeImportEnqueuer:
    return install_enqueuer(app)


async def test_import_returns_202_and_creates_new_project(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await auth(db_session)
    resp = await post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] in {"queued", "running"}
    assert UUID(body["project_id"])
    assert UUID(body["import_id"])
    assert len(enqueuer.calls) == 1
    # The new project exists and is owned by the caller.
    got = await async_client.get(f"/api/v1/projects/{body['project_id']}", headers=headers)
    assert got.status_code == 200


async def test_import_rejects_non_zip_extension_415(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await auth(db_session)
    resp = await post_import(async_client, headers, b"hello", filename="notes.txt", content_type="text/plain")
    assert resp.status_code == 415
    assert len(enqueuer.calls) == 0


async def test_import_rejects_bad_magic_415(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await auth(db_session)
    # .zip extension but octet-stream type and non-PK bytes.
    resp = await post_import(
        async_client,
        headers,
        b"not a zip",
        filename="x.zip",
        content_type="application/octet-stream",
    )
    assert resp.status_code == 415


async def test_import_oversize_413_and_no_orphan_blob(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await auth(db_session)
    settings = get_settings()
    monkeypatch.setattr(settings, "import_max_zip_bytes", 16, raising=False)
    big = make_zip({"main.tex": b"x" * 500})
    resp = await post_import(async_client, headers, big)
    assert resp.status_code == 413
    # The staged blob was best-effort deleted (no orphan).
    assert store._d == {}  # type: ignore[attr-defined]
    assert len(enqueuer.calls) == 0


async def test_requires_auth(async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore) -> None:
    resp = await post_import(async_client, {}, make_zip({"main.tex": b"x"}))
    assert resp.status_code == 401
