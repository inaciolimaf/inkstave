"""Shared helpers for the file-tree API integration tests (spec 12)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore, PutData
from tests.factories import UserFactory


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


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _project(async_client: AsyncClient, headers: dict[str, str]) -> str:
    resp = await async_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)
    return str(resp.json()["id"])


def _tree(pid: str) -> str:
    return f"/api/v1/projects/{pid}/tree"


async def _create(
    client: AsyncClient,
    pid: str,
    headers: dict[str, str],
    *,
    type_: str = "folder",
    name: str,
    parent_id: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {"type": type_, "name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id
    resp = await client.post(f"{_tree(pid)}/entities", json=body, headers=headers)
    return {"status": resp.status_code, "json": resp.json() if resp.content else None}
