"""Shared helpers and fixtures for the binary file API integration tests (spec 14).

Parametrised over the ``local`` backend (tmp dir) and an in-memory store that
stands in for an S3-compatible backend, proving the abstraction is
backend-agnostic (AC10) — no network.

This module is intentionally not ``test_``-prefixed so pytest does not collect
it. The sibling ``test_files_api*.py`` modules import the fixtures and helpers
they need from here to stay DRY.
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
