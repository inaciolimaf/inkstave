"""Opt-in smoke test that runs the REAL Tectonic binary (spec 21).

Excluded from the default fast suite: it only runs when ``RUN_REAL_COMPILE=1``
and a ``tectonic`` binary is on PATH. It proves the binary + bundle/cache wiring
end-to-end and must never threaten the 2-minute budget.

Run it explicitly with:  RUN_REAL_COMPILE=1 pytest backend/tests/smoke -q
"""

from __future__ import annotations

import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from inkstave.compile.packages import load_package_config
from inkstave.compile.result import CompileStatus
from inkstave.compile.runner import LocalTectonicRunner
from inkstave.compile.service import CompileOptions, CompileService
from inkstave.config import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_COMPILE") != "1" or shutil.which("tectonic") is None,
    reason="real Tectonic compile is opt-in (set RUN_REAL_COMPILE=1 with tectonic installed)",
)

MINIMAL = "\\documentclass{article}\\begin{document}hi\\end{document}\n"


class _Docs:
    async def iter_documents(self, project_id: object) -> AsyncIterator[tuple[str, str]]:
        yield "main.tex", MINIMAL


class _Files:
    async def iter_files(
        self, project_id: object
    ) -> AsyncIterator[tuple[str, AsyncIterator[bytes]]]:
        return
        yield  # pragma: no cover


async def test_real_minimal_compile(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, compile_workdir_root=str(tmp_path / "compiles"))  # type: ignore[call-arg]
    runner = LocalTectonicRunner(
        bin_path=settings.tectonic_bin,
        cache_dir=Path(settings.tectonic_cache_dir),
        bundle_url=settings.tectonic_bundle_url or None,
        offline=settings.tectonic_offline,
    )
    service = CompileService(
        settings=settings,
        runner=runner,
        docs=_Docs(),
        files=_Files(),
        packages=load_package_config(Path("infra/tectonic/packages.toml"), settings),
    )
    result = await service.compile(CompileOptions(project_id=uuid4(), timeout_s=120))
    assert result.status is CompileStatus.SUCCESS
    assert result.pdf is not None
