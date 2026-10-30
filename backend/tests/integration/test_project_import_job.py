"""End-to-end project import: the ``import_project_zip`` job run inline (spec 101).

The job runs with a hand-built ctx (mirroring the compile-job tests). Only tiny in-memory
zips.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.infra.storage.base import ObjectStore
from tests.integration._project_import_support import (
    PNG,
    FakeImportEnqueuer,
    auth,
    flatten,
    install_enqueuer,
    install_store,
    make_zip,
    post_import,
    run_job,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def store(app: Any) -> ObjectStore:
    return install_store(app)


@pytest.fixture
def enqueuer(app: Any) -> FakeImportEnqueuer:
    return install_enqueuer(app)


def _assert_round_trip_tree(nodes: dict[str, Any]) -> None:
    """Every entry of the fixture archive landed with the right kind."""
    assert nodes["chapters"]["type"] == "folder"
    assert nodes["figures"]["type"] == "folder"
    assert nodes["main.tex"]["type"] == "doc"
    assert nodes["chapters/intro.tex"]["type"] == "doc"
    assert nodes["refs.bib"]["type"] == "doc"
    assert nodes["figures/diagram.png"]["type"] == "file"


async def test_import_end_to_end_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await auth(db_session)
    zip_bytes = make_zip(
        {
            "main.tex": b"\\documentclass{article}\n\\begin{document}hi\\end{document}",
            "chapters/intro.tex": b"intro text",
            "refs.bib": b"@book{x, title={T}}",
            "figures/diagram.png": PNG,
        }
    )
    body = (await post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]

    await run_job(db_session, store, redis, iid)

    status = await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["status"] == "success"
    assert sbody["entries_imported"] == sbody["entries_total"] == 4

    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    nodes = flatten(tree["root"])
    _assert_round_trip_tree(nodes)

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
    headers = await auth(db_session)
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}", "notes.exe": b"MZbinary"})
    body = (await post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await run_job(db_session, store, redis, iid)

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
    headers = await auth(db_session)
    zip_bytes = make_zip({"paper.tex": b"\\documentclass{article}", "main.tex": b"no class here"})
    body = (await post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await run_job(db_session, store, redis, iid)

    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    nodes = flatten(tree["root"])
    proj = (await async_client.get(f"/api/v1/projects/{pid}", headers=headers)).json()
    assert proj["root_doc_id"] == nodes["paper.tex"]["id"]


async def test_latin1_document_decoded(
    async_client: AsyncClient,
    db_session: AsyncSession,
    store: ObjectStore,
    enqueuer: FakeImportEnqueuer,
    redis: Any,
) -> None:
    headers = await auth(db_session)
    latin = "Élan café".encode("latin-1")
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}\n" + latin})
    body = (await post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await run_job(db_session, store, redis, iid)

    sbody = (await async_client.get(f"/api/v1/projects/{pid}/import/{iid}", headers=headers)).json()
    assert sbody["status"] == "success"
    tree = (await async_client.get(f"/api/v1/projects/{pid}/tree", headers=headers)).json()
    doc_id = flatten(tree["root"])["main.tex"]["id"]
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
    headers = await auth(db_session)
    zip_bytes = make_zip({"main.tex": b"\\documentclass{a}", "../../etc/passwd": b"root:x:0:0"})
    body = (await post_import(async_client, headers, zip_bytes)).json()
    pid, iid = body["project_id"], body["import_id"]
    await run_job(db_session, store, redis, iid)

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
    headers = await auth(db_session)
    body = (await post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))).json()
    pid, iid = body["project_id"], body["import_id"]

    # Soft-delete the project out from under the requester before the job runs.
    from sqlalchemy import func, update

    from inkstave.modules.projects.models.project import Project

    await db_session.execute(update(Project).where(Project.id == UUID(pid)).values(deleted_at=func.now()))
    await db_session.commit()

    await run_job(db_session, store, redis, iid)
    # Status read directly (the project is soft-deleted, so the API 404s).
    from inkstave.modules.projects.transfer.repository import ProjectImportRepository

    row = await ProjectImportRepository(db_session).get_by_id(UUID(iid))
    assert row is not None
    assert row.status == "error"


async def test_sse_stream_emits_snapshot_then_terminal(redis: Any) -> None:
    """AC11 — the SSE stream yields a snapshot, then transitions, then closes (no hang)."""
    from uuid import uuid4

    from inkstave.modules.projects.transfer.stream import publish_status, sse_stream

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
    headers = await auth(db_session)
    # A project with no import.
    pid = (await async_client.post("/api/v1/projects", json={"name": "P"}, headers=headers)).json()["id"]
    assert (await async_client.get(f"/api/v1/projects/{pid}/import", headers=headers)).status_code == 404

    body = (await post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))).json()
    latest = await async_client.get(f"/api/v1/projects/{body['project_id']}/import", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["import_id"] == body["import_id"]
