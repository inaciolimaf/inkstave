"""Shared helpers for OutputStore integration tests (spec 23).

Not ``test_``-prefixed so pytest does not collect it. Imported by the
``test_compile_outputs*`` sibling modules to keep the suite DRY.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
