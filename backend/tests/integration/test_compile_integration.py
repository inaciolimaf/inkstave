"""Integration: CompileService with the real spec-13/14 source adapters (spec 21)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.compile.packages import load_package_config
from inkstave.compile.result import CompileStatus, RunOutcome
from inkstave.compile.service import CompileOptions, CompileService
from inkstave.compile.sources import DbDocumentSource, StorageFileSource
from inkstave.config import Settings
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services import file_service
from inkstave.services.document_service import replace_content
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity, ensure_root
from inkstave.storage.local import LocalObjectStore
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeRunner:
    def __init__(self, outcome: RunOutcome, writes: dict[str, bytes]) -> None:
        self._outcome = outcome
        self._writes = writes

    async def run(self, *, output_dir: Path, **_kw: object) -> RunOutcome:
        for rel, data in self._writes.items():
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return self._outcome


def _byte_reader(data: bytes):
    state = {"pos": 0}

    async def read(size: int = -1) -> bytes:
        start = state["pos"]
        chunk = data[start:] if size < 0 else data[start : start + size]
        state["pos"] += len(chunk)
        return chunk

    return read


async def _seed_project(db_session: AsyncSession, store: LocalObjectStore):
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "Paper")
    root = await ensure_root(db_session, project.id)
    main = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", root.id)
    await replace_content(
        db_session,
        project.id,
        main.id,
        "\\documentclass{article}\\begin{document}hi\\end{document}",
        base_version=0,
    )
    folder = await create_entity(db_session, project.id, TreeEntityType.folder, "img", root.id)
    await file_service.upload_file(
        db_session,
        store,
        project.id,
        folder.id,
        "logo.png",
        _byte_reader(PNG),
        "image/png",
        "logo.png",
    )
    return project


def _service(db_session: AsyncSession, store: LocalObjectStore, runner: FakeRunner, tmp: Path):
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp / "compiles"))  # type: ignore[call-arg]
    return CompileService(
        settings=settings,
        runner=runner,
        docs=DbDocumentSource(db_session),
        files=StorageFileSource(db_session, store),
        packages=load_package_config(tmp / "none.toml", settings),
    )


async def test_assembles_docs_and_files_then_succeeds(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    project = await _seed_project(db_session, store)

    runner = FakeRunner(
        RunOutcome(
            exit_code=0, stdout="", stderr="", timed_out=False, cancelled=False, duration_ms=5
        ),
        {"main.pdf": b"%PDF-1.7", "main.log": b"ok"},
    )
    cid = uuid4()
    service = _service(db_session, store, runner, tmp_path)
    result = await service.compile(
        CompileOptions(project_id=project.id, compile_id=cid, keep_workdir=True)
    )

    assert result.status is CompileStatus.SUCCESS
    assert result.pdf is not None
    workdir = result.workdir
    assert workdir is not None
    assert (workdir / "input" / "main.tex").read_text().startswith("\\documentclass")
    assert (workdir / "input" / "img" / "logo.png").read_bytes() == PNG


async def test_default_cleanup_removes_workdir(db_session: AsyncSession, tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    project = await _seed_project(db_session, store)
    runner = FakeRunner(
        RunOutcome(
            exit_code=0, stdout="", stderr="", timed_out=False, cancelled=False, duration_ms=5
        ),
        {"main.pdf": b"%PDF"},
    )
    cid = uuid4()
    service = _service(db_session, store, runner, tmp_path)
    result = await service.compile(CompileOptions(project_id=project.id, compile_id=cid))
    assert result.status is CompileStatus.SUCCESS
    assert not (tmp_path / "compiles" / str(cid)).exists()
