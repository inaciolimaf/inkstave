"""Integration tests for the compile output HTTP endpoints (spec 23)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileArtifact, CompileResult, CompileStatus
from inkstave.config import Settings, get_settings
from inkstave.dependencies import get_object_store
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.7\n0123456789abcdef"  # 24 bytes
LOG = b"the compile log\n"


@pytest.fixture
def backend(app: Any, tmp_path: Path) -> LocalObjectStore:
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    app.dependency_overrides[get_object_store] = lambda: store
    return store


def _result(tmp_path: Path, *, with_pdf: bool = True) -> CompileResult:
    outdir = tmp_path / "wd" / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    if with_pdf:
        (outdir / "output.pdf").write_bytes(PDF)
        artifacts.append(
            CompileArtifact(
                "output.pdf", "output.pdf", outdir / "output.pdf", len(PDF), "application/pdf"
            )
        )
    (outdir / "main.log").write_bytes(LOG)
    artifacts.append(
        CompileArtifact("main.log", "main.log", outdir / "main.log", len(LOG), "text/plain")
    )
    pdf = artifacts[0] if with_pdf else None
    return CompileResult(
        status=CompileStatus.SUCCESS if with_pdf else CompileStatus.FAILURE,
        pdf=pdf,
        log_text="log",
        stdout="",
        stderr="",
        exit_code=0 if with_pdf else 1,
        duration_ms=1,
        artifacts=artifacts,
    )


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}", "_uid": str(user.id)}


async def _seed_compile(
    db_session: AsyncSession,
    backend: LocalObjectStore,
    tmp_path: Path,
    owner_id: str,
    *,
    with_pdf: bool = True,
):
    from uuid import UUID

    project = await __import__(
        "inkstave.services.project", fromlist=["create_project"]
    ).create_project(db_session, UUID(owner_id), "P")
    row = await CompileRepository(db_session).create(
        project_id=project.id, requested_by=UUID(owner_id), main_file="main.tex"
    )
    store = OutputStore(
        storage=backend,
        repo=OutputRepository(db_session),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
    )
    await store.persist(row.id, project.id, _result(tmp_path, with_pdf=with_pdf))
    return project, row


def _url(pid: str, cid: str) -> str:
    return f"/api/v1/projects/{pid}/compile/{cid}"


async def test_list_outputs(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), str(row.id)) + "/outputs", headers=headers)
    assert resp.status_code == 200
    kinds = {o["kind"] for o in resp.json()}
    assert kinds == {"pdf", "log"}


async def test_pdf_full_200(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _url(str(project.id), str(row.id)) + "/output.pdf", headers=headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.headers["content-length"] == str(len(PDF))
    assert "etag" in resp.headers
    assert resp.content == PDF


async def test_pdf_range_206(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _url(str(project.id), str(row.id)) + "/output.pdf",
        headers={**headers, "Range": "bytes=0-4"},
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == f"bytes 0-4/{len(PDF)}"
    assert resp.content == PDF[:5]


async def test_pdf_unsatisfiable_416(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _url(str(project.id), str(row.id)) + "/output.pdf",
        headers={**headers, "Range": f"bytes={len(PDF)}-{len(PDF) + 10}"},
    )
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{len(PDF)}"


async def test_pdf_conditional_304(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    url = _url(str(project.id), str(row.id)) + "/output.pdf"
    first = await async_client.get(url, headers=headers)
    etag = first.headers["etag"]
    resp = await async_client.get(url, headers={**headers, "If-None-Match": etag})
    assert resp.status_code == 304
    assert resp.content == b""


async def test_log_200(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _url(str(project.id), str(row.id)) + "/output.log", headers=headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/plain; charset=utf-8"
    assert resp.content == LOG


async def test_pdf_404_for_failed_compile(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed_compile(
        db_session, backend, tmp_path, headers["_uid"], with_pdf=False
    )
    resp = await async_client.get(
        _url(str(project.id), str(row.id)) + "/output.pdf", headers=headers
    )
    assert resp.status_code == 404


async def test_cross_user_is_404(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    other = await _auth(db_session)
    project, row = await _seed_compile(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), str(row.id)) + "/output.pdf", headers=other)
    assert resp.status_code == 404
