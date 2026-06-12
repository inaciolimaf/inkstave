"""Integration tests for project import from a .zip archive (spec 101).

The ARQ worker is never used: the upload endpoint stages the blob and a fake
enqueuer records the call; the ``import_project_zip`` job is then run inline with
a hand-built ctx (mirroring the compile-job tests). Only tiny in-memory zips.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.config import get_settings
from inkstave.dependencies import get_import_enqueuer, get_object_store
from inkstave.services.import_jobs import import_project_zip
from inkstave.storage.base import ObjectStore
from tests.factories import UserFactory
from tests.integration._files_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration

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


@pytest_asyncio.fixture
async def store(app: Any) -> ObjectStore:
    s = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: s
    return s


@pytest.fixture
def enqueuer(app: Any) -> FakeImportEnqueuer:
    fake = FakeImportEnqueuer()
    app.dependency_overrides[get_import_enqueuer] = lambda: fake
    return fake


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def _post_import(
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


async def _run_job(
    db_session: AsyncSession, store: ObjectStore, redis: Any, import_id: str
) -> None:
    ctx = {
        "settings": get_settings(),
        "redis": redis,
        "object_store": store,
        "session_factory": lambda: _SessionCtx(db_session),
    }
    await import_project_zip(ctx, import_id)


def _flatten(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for child in node.get("children") or []:
        out[child["path"]] = child
        out.update(_flatten(child))
    return out


# --------------------------------------------------------------------------- #
# Upload endpoint
# --------------------------------------------------------------------------- #


async def test_import_returns_202_and_creates_new_project(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await _auth(db_session)
    resp = await _post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
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
    headers = await _auth(db_session)
    resp = await _post_import(
        async_client, headers, b"hello", filename="notes.txt", content_type="text/plain"
    )
    assert resp.status_code == 415
    assert len(enqueuer.calls) == 0


async def test_import_rejects_bad_magic_415(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await _auth(db_session)
    # .zip extension but octet-stream type and non-PK bytes.
    resp = await _post_import(
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
    headers = await _auth(db_session)
    settings = get_settings()
    monkeypatch.setattr(settings, "import_max_zip_bytes", 16, raising=False)
    big = make_zip({"main.tex": b"x" * 500})
    resp = await _post_import(async_client, headers, big)
    assert resp.status_code == 413
    # The staged blob was best-effort deleted (no orphan).
    assert store._d == {}  # type: ignore[attr-defined]
    assert len(enqueuer.calls) == 0


async def test_requires_auth(
    async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    resp = await _post_import(async_client, {}, make_zip({"main.tex": b"x"}))
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# End-to-end via inline job
# --------------------------------------------------------------------------- #


async def test_import_end_to_end_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await _auth(db_session)
    zip_bytes = make_zip(
        {
            "main.tex": b"\\documentclass{article}\n\\begin{document}hi\\end{document}",
            "chapters/intro.tex": b"intro text",
            "refs.bib": b"@book{x, title={T}}",
            "figures/diagram.png": PNG,
        }
    )
    resp = await _post_import(async_client, headers, zip_bytes)
    body = resp.json()
    pid, iid = body["project_id"], body["import_id"]

    await _run_job(db_session, store, redis, iid)

    status = await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["status"] == "success"
    assert sbody["entries_imported"] == sbody["entries_total"] == 4

    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    nodes = _flatten(tree["root"])
    assert nodes["chapters"]["type"] == "folder"
    assert nodes["figures"]["type"] == "folder"
    assert nodes["main.tex"]["type"] == "doc"
    assert nodes["chapters/intro.tex"]["type"] == "doc"
    assert nodes["refs.bib"]["type"] == "doc"
    assert nodes["figures/diagram.png"]["type"] == "file"

    # root_doc_id points at the main.tex doc entity.
    proj = (await async_client.get(f"/api/v1/projects/{pid}", headers=headers)).json()
    assert proj["root_doc_id"] == nodes["main.tex"]["id"]

    # The stored blob bytes equal the PNG.
    png_id = nodes["figures/diagram.png"]["id"]
    dl = await async_client.get(f"/api/v1/projects/{pid}/files/{png_id}/content", headers=headers)
    assert dl.status_code == 200
    assert dl.content == PNG

    # The doc content was decoded and seeded.
    doc_id = nodes["chapters/intro.tex"]["id"]
    doc = await async_client.get(f"/api/v1/projects/{pid}/documents/{doc_id}", headers=headers)
    assert doc.json()["content"] == "intro text"


async def test_import_partial_when_entry_skipped(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await _auth(db_session)
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}", "notes.exe": b"MZbinary"})
    body = (await _post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await _run_job(db_session, store, redis, iid)

    sbody = (await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)).json()
    assert sbody["status"] == "partial"
    assert sbody["entries_imported"] < sbody["entries_total"]


async def test_root_doc_documentclass_precedence(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await _auth(db_session)
    zip_bytes = make_zip({"paper.tex": b"\\documentclass{article}", "main.tex": b"no class here"})
    body = (await _post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await _run_job(db_session, store, redis, iid)

    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    nodes = _flatten(tree["root"])
    proj = (await async_client.get(f"/api/v1/projects/{pid}", headers=headers)).json()
    assert proj["root_doc_id"] == nodes["paper.tex"]["id"]


async def test_latin1_document_decoded(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await _auth(db_session)
    latin = "Élan café".encode("latin-1")
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}\n" + latin})
    body = (await _post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await _run_job(db_session, store, redis, iid)

    sbody = (await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)).json()
    assert sbody["status"] == "success"
    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    doc_id = _flatten(tree["root"])["main.tex"]["id"]
    doc = await async_client.get(f"/api/v1/projects/{pid}/documents/{doc_id}", headers=headers)
    assert "Élan café" in doc.json()["content"]


async def test_zip_slip_writes_nothing(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    """AC13 — a malicious zip-slip archive imports nothing (no rows, no blobs)."""
    headers = await _auth(db_session)
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}", "../../etc/passwd": b"root:x:0:0"})
    body = (await _post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await _run_job(db_session, store, redis, iid)

    sbody = (await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)).json()
    assert sbody["status"] == "failure"
    assert sbody["error_type"] == "zip_slip"
    # Nothing reconstructed: only the project's root folder exists; no file blobs.
    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    assert (tree["root"].get("children") or []) == []
    assert all(not k.startswith(f"projects/{pid}/files/") for k in store._d)  # type: ignore[attr-defined]


async def test_ownership_defence_marks_error(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await _auth(db_session)
    body = (
        await _post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
    ).json()
    pid, iid = body["project_id"], body["import_id"]

    # Soft-delete the project out from under the requester before the job runs.
    from sqlalchemy import func, update

    from inkstave.db.models.project import Project

    await db_session.execute(
        update(Project).where(Project.id == UUID(pid)).values(deleted_at=func.now())
    )
    await db_session.commit()

    await _run_job(db_session, store, redis, iid)
    # Status read directly (the project is soft-deleted, so the API 404s).
    from inkstave.services.import_repository import ProjectImportRepository

    row = await ProjectImportRepository(db_session).get_by_id(UUID(iid))
    assert row is not None
    assert row.status == "error"


async def test_sse_stream_emits_snapshot_then_terminal(redis: Any) -> None:
    """AC11 — the SSE stream yields a snapshot, then transitions, then closes (no hang)."""
    from uuid import uuid4

    from inkstave.services.import_stream import publish_status, sse_stream

    iid = uuid4()

    async def snapshot() -> dict[str, Any]:
        return {"status": "running"}

    gen = sse_stream(redis, iid, snapshot, keepalive_seconds=5)
    first = await anext(gen)
    assert b'"status": "running"' in first

    await publish_status(redis, iid, {"status": "success"})
    second = await anext(gen)
    assert b'"status": "success"' in second

    with pytest.raises(StopAsyncIteration):  # terminal closes the stream
        await anext(gen)


async def test_latest_404_then_returns(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
) -> None:
    headers = await _auth(db_session)
    # A project with no import.
    pid = (await async_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()[
        "id"
    ]
    assert (
        await async_client.get(f"/api/v1/projects/{pid}/import", headers=headers)
    ).status_code == 404

    body = (
        await _post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
    ).json()
    latest = await async_client.get(
        f"/api/v1/projects/{body['project_id']}/import", headers=headers
    )
    assert latest.status_code == 200
    assert latest.json()["import_id"] == body["import_id"]
