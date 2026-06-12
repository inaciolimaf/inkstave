"""Integration tests for the SyncTeX HTTP endpoints (spec 26)."""

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
from tests.synctex_fixtures import MULTI_FILE, SINGLE_FILE, gz

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
    synctex_text: str = SINGLE_FILE,
    with_synctex: bool = True,
):
    project = await create_project(db_session, UUID(owner_id), "P")
    repo = CompileRepository(db_session)
    row = await repo.create(
        project_id=project.id, requested_by=UUID(owner_id), main_file="main.tex"
    )
    await repo.update(row, status="success", has_pdf=True)

    outdir = tmp_path / "wd" / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    pdf_path = outdir / "output.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    artifacts = [CompileArtifact("output.pdf", "output.pdf", pdf_path, 8, "application/pdf")]
    if with_synctex:
        sx_path = outdir / "output.synctex.gz"
        sx_path.write_bytes(gz(synctex_text))
        artifacts.append(
            CompileArtifact(
                "output.synctex.gz",
                "output.synctex.gz",
                sx_path,
                sx_path.stat().st_size,
                "application/gzip",
            )
        )
    result = CompileResult(
        status=CompileStatus.SUCCESS,
        pdf=artifacts[0],
        log_text="",
        stdout="",
        stderr="",
        exit_code=0,
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


def _fwd(pid: str) -> str:
    return f"/api/v1/projects/{pid}/synctex/code-to-pdf"


def _inv(pid: str) -> str:
    return f"/api/v1/projects/{pid}/synctex/pdf-to-code"


# --- forward (code -> pdf) ------------------------------------------------- #


async def test_forward_same_file(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _fwd(str(project.id)), params={"file": "main.tex", "line": 10}, headers=headers
    )
    assert resp.status_code == 200
    boxes = resp.json()["boxes"]
    assert boxes and boxes[0]["page"] == 1
    assert abs(boxes[0]["v"] - 200.0) <= 1.0


async def test_forward_nearest_line(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _fwd(str(project.id)), params={"file": "main.tex", "line": 15}, headers=headers
    )
    assert resp.status_code == 200
    assert abs(resp.json()["boxes"][0]["v"] - 400.0) <= 1.0


async def test_forward_unknown_file_is_no_match(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _fwd(str(project.id)), params={"file": "nope.tex", "line": 1}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "no_match"


async def test_forward_bad_params_422(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _fwd(str(project.id)), params={"file": "main.tex", "line": 0}, headers=headers
    )
    assert resp.status_code == 422


# --- inverse (pdf -> code) ------------------------------------------------- #


async def test_inverse_inside_box(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _inv(str(project.id)), params={"page": 1, "h": 150.0, "v": 201.0}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"] == "main.tex"
    assert body["line"] == 10


async def test_inverse_nearest(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(
        _inv(str(project.id)), params={"page": 1, "h": 1000.0, "v": 1000.0}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["line"] == 20


async def test_inverse_multi_file(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(
        db_session, backend, tmp_path, headers["_uid"], synctex_text=MULTI_FILE
    )
    resp = await async_client.get(
        _inv(str(project.id)), params={"page": 1, "h": 150.0, "v": 401.0}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["file"] == "sections/intro.tex"
    assert body["line"] == 5


# --- no synctex / auth ----------------------------------------------------- #


async def test_forward_no_synctex_is_unavailable(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"], with_synctex=False)
    resp = await async_client.get(
        _fwd(str(project.id)), params={"file": "main.tex", "line": 10}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "synctex_unavailable"


async def test_inverse_no_synctex_is_unavailable(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"], with_synctex=False)
    resp = await async_client.get(
        _inv(str(project.id)), params={"page": 1, "h": 1.0, "v": 1.0}, headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["message"] == "synctex_unavailable"


async def test_requires_auth(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    resp = await async_client.get(_fwd(str(project.id)), params={"file": "main.tex", "line": 10})
    assert resp.status_code == 401


async def test_non_member_is_denied(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    other = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    # The Phase-2 access dependency returns 404 (not 403) for a non-member by
    # deliberate anti-enumeration design (ADR 0026): a non-member must not be able
    # to tell "exists-but-forbidden" (403) from "no such project" (404), so both
    # collapse to 404. This is a KNOWING deviation from spec 26 criterion 8, which
    # as written expects 403 for a non-member; we intentionally keep 404 because a
    # 403 would leak project existence. The router carries the matching rationale.
    resp = await async_client.get(
        _fwd(str(project.id)),
        params={"file": "main.tex", "line": 10},
        headers=other,
    )
    assert resp.status_code == 404  # 404 by design (see comment above), not 403


# --- coordinate round-trip over HTTP (criterion 9) ------------------------- #


async def test_round_trip_over_http(
    async_client: AsyncClient, db_session: AsyncSession, backend: LocalObjectStore, tmp_path: Path
) -> None:
    headers = await _auth(db_session)
    project, _ = await _seed(db_session, backend, tmp_path, headers["_uid"])
    fwd = await async_client.get(
        _fwd(str(project.id)), params={"file": "main.tex", "line": 10}, headers=headers
    )
    box = fwd.json()["boxes"][0]
    inv = await async_client.get(
        _inv(str(project.id)),
        params={"page": box["page"], "h": box["h"], "v": box["v"]},
        headers=headers,
    )
    assert inv.status_code == 200
    assert inv.json()["line"] == 10
