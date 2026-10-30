"""Shared helpers for the project-import integration tests (spec 101)."""

from __future__ import annotations

import io
import zipfile
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_import_enqueuer, get_object_store
from inkstave.services.import_jobs import import_project_zip
from inkstave.storage.base import ObjectStore
from tests.factories import UserFactory
from tests.integration._files_api_support import InMemoryObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class FakeImportEnqueuer:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    async def enqueue(self, import_id: UUID) -> str | None:
        self.calls.append(import_id)
        return f"job-{import_id}"


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def install_store(app: Any) -> ObjectStore:
    s = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: s
    return s


def install_enqueuer(app: Any) -> FakeImportEnqueuer:
    fake = FakeImportEnqueuer()
    app.dependency_overrides[get_import_enqueuer] = lambda: fake
    return fake


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


async def auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def post_import(
    client: AsyncClient,
    headers: dict[str, str],
    zip_bytes: bytes,
    *,
    filename: str = "paper.zip",
    content_type: str = "application/zip",
    name: str | None = None,
) -> Any:
    files = {"file": (filename, zip_bytes, content_type)}
    data = {"name": name} if name is not None else {}
    return await client.post("/api/v1/projects/import", files=files, data=data, headers=headers)


async def run_job(db_session: AsyncSession, store: ObjectStore, redis: Any, import_id: str) -> None:
    ctx = {
        "settings": get_settings(),
        "redis": redis,
        "object_store": store,
        "session_factory": lambda: _SessionCtx(db_session),
    }
    await import_project_zip(ctx, import_id)


def flatten(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for child in node.get("children") or []:
        out[child["path"]] = child
        out.update(flatten(child))
    return out
