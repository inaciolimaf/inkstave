"""Compiling a lived-in multi-file project: the assembled source tree holds every seeded file.

The runner is a fake (the mock compile mode): no Tectonic process runs in the fast tiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import Settings
from inkstave.infra.storage.local import LocalObjectStore
from inkstave.modules.compile.assembly.sources import DbDocumentSource, StorageFileSource
from inkstave.modules.compile.deps import get_compile_enqueuer
from inkstave.modules.compile.running.packages import load_package_config
from inkstave.modules.compile.running.result import CompileStatus, RunOutcome
from inkstave.modules.compile.running.service import CompileOptions, CompileService
from tests.factories.lived_in import DOC_CONTENTS, FILE_PATH, MAIN_TEX, PLOT_PNG, build_lived_in_project
from tests.integration._seeded_support import auth_headers

pytestmark = pytest.mark.integration


class _FakeRunner:
    """Stands in for Tectonic: succeeds and writes a PDF, so the assembled input is what the test checks."""

    async def run(self, *, output_dir: Path, **_kw: object) -> RunOutcome:
        (output_dir / "main.pdf").write_bytes(b"%PDF-1.7")
        return RunOutcome(exit_code=0, stdout="", stderr="", timed_out=False, cancelled=False, duration_ms=1)


class _FakeEnqueuer:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def enqueue(self, compile_id: object) -> str | None:
        self.calls.append(compile_id)
        return "job"


async def test_seeded_compile_assembles_every_seeded_file(db_session: AsyncSession, tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    lived = await build_lived_in_project(db_session, store)
    await db_session.commit()
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp_path / "compiles"))  # type: ignore[call-arg]
    service = CompileService(
        settings=settings,
        runner=_FakeRunner(),  # type: ignore[arg-type]
        docs=DbDocumentSource(db_session),
        files=StorageFileSource(db_session, store),
        packages=load_package_config(tmp_path / "none.toml", settings),
    )

    result = await service.compile(
        CompileOptions(project_id=lived.project_id, compile_id=uuid4(), keep_workdir=True)
    )

    assert result.status is CompileStatus.SUCCESS
    workdir = result.workdir
    assert workdir is not None
    source = workdir / "input"
    assert (source / "main.tex").read_text(encoding="utf-8") == MAIN_TEX
    for path, text in DOC_CONTENTS.items():
        assert (source / path).read_bytes() == text.encode("utf-8"), path
    assert (source / FILE_PATH).read_bytes() == PLOT_PNG


async def test_seeded_compile_request_is_queued_for_the_main_document(
    app: Any, async_client: AsyncClient, lived_in_project: Any, lived_in_store: Any
) -> None:
    enqueuer = _FakeEnqueuer()
    app.dependency_overrides[get_compile_enqueuer] = lambda: enqueuer
    headers = auth_headers(lived_in_project.owner)

    resp = await async_client.post(
        f"/api/v1/projects/{lived_in_project.project_id}/compile", json={}, headers=headers
    )

    assert resp.status_code == 202
    assert resp.json()["main_file"] == "main.tex"
    assert len(enqueuer.calls) == 1
