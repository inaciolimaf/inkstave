"""COMPILE_MAX_OUTPUT_BYTES is enforced on the collected outputs (spec 21/23)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from inkstave.modules.compile.running.result import CompileStatus
from inkstave.modules.compile.running.service import CompileOptions
from tests.unit.test_compile_service import FakeRunner, build_service, ok_outcome

_PDF = b"%PDF-1.7" + b"x" * 400


async def test_outputs_over_the_cap_fail_the_compile(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": _PDF, "main.log": b"log"})
    service = build_service(tmp_path, runner, [("main.tex", "hi")], compile_max_output_bytes=100)

    result = await service.compile(CompileOptions(project_id=uuid4()))

    assert result.status is CompileStatus.SYSTEM_ERROR
    assert result.pdf is None
    assert result.log_text.startswith("output too large")
    assert "COMPILE_MAX_OUTPUT_BYTES" in result.log_text


async def test_outputs_within_the_cap_still_succeed(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": _PDF, "main.log": b"log"})
    service = build_service(tmp_path, runner, [("main.tex", "hi")], compile_max_output_bytes=10_000)

    result = await service.compile(CompileOptions(project_id=uuid4()))

    assert result.status is CompileStatus.SUCCESS
    assert result.pdf is not None
