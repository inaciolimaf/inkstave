"""Integration tests for the compile-problems endpoint (spec 27)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

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
from inkstave.services.project import create_project
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory
from tests.logparse_fixtures import SAMPLE_LOG

pytestmark = pytest.mark.integration


@pytest.fixture
def backend(app: Any, tmp_path: Path) -> LocalObjectStore:
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    app.dependency_overrides[get_object_store] = lambda: store
    return store


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}", "_uid": str(user.id)}


async def _seed(
    db_session: AsyncSession,
    backend: LocalObjectStore,
    tmp_path: Path,
    owner_id: str,
    *,
    with_log: bool = True,
):
    project = await create_project(db_session, UUID(owner_id), "P")
    repo = CompileRepository(db_session)
    row = await repo.create(
        project_id=project.id, requested_by=UUID(owner_id), main_file="main.tex"
    )
    await repo.update(row, status="failure")

    outdir = tmp_path / "wd" / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    if with_log:
        log_path = outdir / "main.log"
        log_path.write_bytes(SAMPLE_LOG.encode())
        artifacts.append(
            CompileArtifact("main.log", "main.log", log_path, log_path.stat().st_size, "text/plain")
        )
    else:
        pdf_path = outdir / "output.pdf"
        pdf_path.write_bytes(b"%PDF-1.7")
        artifacts.append(
            CompileArtifact("output.pdf", "output.pdf", pdf_path, 8, "application/pdf")
        )

    result = CompileResult(
        status=CompileStatus.FAILURE,
        pdf=None,
        log_text="",
        stdout="",
        stderr="",
        exit_code=1,
        duration_ms=1,
        artifacts=artifacts,
    )
    store = OutputStore(
        storage=backend,
        repo=OutputRepository(db_session),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
    )
    await store.persist(row.id, project.id, result)
    await db_session.commit()
    return project, row


def _url(pid: str, cid: str) -> str:
    return f"/api/v1/projects/{pid}/compiles/{cid}/problems"


async def test_problems_by_id(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), str(row.id)), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["compile_id"] == str(row.id)
    assert body["errors"] == 1
    assert body["warnings"] == 2
    assert body["infos"] == 1
    rules = [p["rule"] for p in body["problems"]]
    assert "tex-error" in rules and "undefined-ref" in rules


async def test_problems_latest_alias(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), "latest"), headers=headers)
    assert resp.status_code == 200
    assert resp.json()["errors"] == 1


async def test_problems_no_log_is_404(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed(db_session, backend, tmp_path, headers["_uid"], with_log=False)
    resp = await async_client.get(_url(str(project.id), str(row.id)), headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "log_unavailable"


async def test_problems_requires_auth(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, row = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), str(row.id)))
    assert resp.status_code == 401


async def test_problems_non_member_denied(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    other = await _auth(db_session)
    project, row = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_url(str(project.id), str(row.id)), headers=other)
    assert resp.status_code == 404  # anti-enumeration: 404, not 403 (ADR 0007)
