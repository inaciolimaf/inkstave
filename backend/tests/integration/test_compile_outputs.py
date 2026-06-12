"""Integration tests for OutputStore persistence + retention (spec 23)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.output_repository import OutputRepository
from inkstave.compile.outputs import OutputStore
from inkstave.compile.repository import CompileRepository
from inkstave.compile.result import CompileArtifact, CompileResult, CompileStatus
from inkstave.config import Settings
from inkstave.db.models.compile import Compile
from inkstave.db.models.compile_output import CompileOutput
from inkstave.services.project import create_project
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

FILES = {
    "output.pdf": (b"%PDF-1.7\n0123456789abcdef", "application/pdf"),
    "main.log": (b"this is the log", "text/plain"),
    "main.synctex.gz": (b"\x1f\x8b\x08\x00", "application/gzip"),
    "main.aux": (b"\\relax", "text/plain"),
}


def _result(tmp_path: Path) -> CompileResult:
    outdir = tmp_path / "wd" / "output"
    outdir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name, (data, ct) in FILES.items():
        path = outdir / name
        path.write_bytes(data)
        artifacts.append(CompileArtifact(name, name, path, len(data), ct))
    return CompileResult(
        status=CompileStatus.SUCCESS,
        pdf=artifacts[0],
        log_text="log",
        stdout="",
        stderr="",
        exit_code=0,
        duration_ms=1,
        artifacts=artifacts,
    )


async def _seed(db_session: AsyncSession):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    row = await CompileRepository(db_session).create(
        project_id=project.id, requested_by=user.id, main_file="main.tex"
    )
    return user, project, row


def _store(db_session: AsyncSession, tmp_path: Path) -> OutputStore:
    return OutputStore(
        storage=LocalObjectStore(tmp_path / "blobs", 65536),
        repo=OutputRepository(db_session),
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
    )


async def _collect(stream) -> bytes:
    return b"".join([c async for c in stream])


async def test_persist_records_rows_and_bytes(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))

    assert len(rows) == 4
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"pdf", "log", "synctex", "aux"}
    assert by_kind["pdf"].content_type == "application/pdf"
    assert by_kind["pdf"].size_bytes == len(FILES["output.pdf"][0])
    assert len(by_kind["pdf"].etag) == 64  # sha256 hex
    assert by_kind["pdf"].storage_key == f"compiles/{project.id}/{compile_row.id}/output.pdf"

    pdf = await store.open_pdf(compile_row.id)
    assert pdf is not None
    assert await _collect(pdf.read_range(0, pdf.size - 1)) == FILES["output.pdf"][0]
    assert await _collect(pdf.read_range(0, 4)) == FILES["output.pdf"][0][:5]


async def test_persist_is_idempotent(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    await store.persist(compile_row.id, project.id, _result(tmp_path))
    await store.persist(compile_row.id, project.id, _result(tmp_path))
    assert len(await store.list_outputs(compile_row.id)) == 4


async def test_delete_for_compile_removes_rows_and_objects(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    assert await backend.exists(rows[0].storage_key)

    await store.delete_for_compile(compile_row.id)
    assert await store.list_outputs(compile_row.id) == []
    assert await backend.exists(rows[0].storage_key) is False


async def test_delete_for_project_sweeps_storage(db_session: AsyncSession, tmp_path: Path) -> None:
    _, project, compile_row = await _seed(db_session)
    store = _store(db_session, tmp_path)
    rows = await store.persist(compile_row.id, project.id, _result(tmp_path))
    backend = LocalObjectStore(tmp_path / "blobs", 65536)

    await store.delete_for_project(project.id)
    assert await backend.exists(rows[0].storage_key) is False


async def _compile_with_output(
    db_session: AsyncSession, project_id, user_id, created_at: datetime
) -> Compile:
    row = Compile(
        project_id=project_id,
        requested_by=user_id,
        main_file="main.tex",
        status="success",
        created_at=created_at,
    )
    db_session.add(row)
    await db_session.flush()
    db_session.add(
        CompileOutput(
            compile_id=row.id,
            project_id=project_id,
            name="output.pdf",
            rel_path="output.pdf",
            kind="pdf",
            content_type="application/pdf",
            size_bytes=1,
            storage_key=f"compiles/{project_id}/{row.id}/output.pdf",
            etag="x",
        )
    )
    await db_session.flush()
    return row


async def test_retention_selects_beyond_keep_window(
    db_session: AsyncSession,
) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    rows = [
        await _compile_with_output(db_session, project.id, user.id, now - timedelta(minutes=i))
        for i in range(4)  # i=0 newest ... i=3 oldest
    ]
    repo = OutputRepository(db_session)
    pruned = await repo.list_compiles_for_retention(
        keep_per_project=2, max_age_cutoff=now - timedelta(days=365), batch=10
    )
    # Keep the 2 newest; the 2 oldest are selected, oldest first.
    assert pruned == [rows[3].id, rows[2].id]


class _SessionCtx:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _StubService:
    def __init__(self, result: CompileResult) -> None:
        self._result = result

    async def compile(self, opts: object, cancel: object) -> CompileResult:
        return self._result


async def test_job_persists_outputs_and_cleans_workdir(
    db_session: AsyncSession, redis, tmp_path: Path
) -> None:
    from inkstave.compile.jobs import run_compile

    _, project, compile_row = await _seed(db_session)
    result = _result(tmp_path)
    result.workdir = tmp_path / "wd"  # the job cleans this up after persisting
    backend = LocalObjectStore(tmp_path / "blobs", 65536)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    async def persist(session: AsyncSession, cid, pid, res: CompileResult) -> None:
        await OutputStore(
            storage=backend, repo=OutputRepository(session), settings=settings
        ).persist(cid, pid, res)

    ctx = {
        "settings": settings,
        "redis": redis,
        "session_factory": lambda: _SessionCtx(db_session),
        "make_compile_service": lambda _s: _StubService(result),
        "persist_hook": persist,
    }
    await run_compile(ctx, str(compile_row.id))

    row = await CompileRepository(db_session).get_by_id(compile_row.id)
    assert row is not None
    assert row.status == "success"
    assert row.has_pdf is True
    store = OutputStore(storage=backend, repo=OutputRepository(db_session), settings=settings)
    assert len(await store.list_outputs(compile_row.id)) == 4
    assert not (tmp_path / "wd").exists()  # workdir removed after persistence


async def test_retention_selects_by_age(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    now = datetime.now(UTC)
    old = await _compile_with_output(db_session, project.id, user.id, now - timedelta(days=40))
    await _compile_with_output(db_session, project.id, user.id, now)
    repo = OutputRepository(db_session)
    pruned = await repo.list_compiles_for_retention(
        keep_per_project=100, max_age_cutoff=now - timedelta(days=30), batch=10
    )
    assert pruned == [old.id]  # only the aged-out one, despite a generous keep window
