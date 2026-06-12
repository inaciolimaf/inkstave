"""Unit tests for CompileService orchestration with a fake runner (spec 21)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

from inkstave.compile.limits import CancelToken
from inkstave.compile.packages import load_package_config
from inkstave.compile.result import CompileStatus, RunOutcome
from inkstave.compile.service import CompileOptions, CompileService
from inkstave.config import Settings


def make_settings(tmp_path: Path, **over: object) -> Settings:
    return Settings(_env_file=None, compile_workdir_root=str(tmp_path), **over)  # type: ignore[call-arg]


class FakeDocs:
    def __init__(self, docs: list[tuple[str, str]]) -> None:
        self._docs = docs

    async def iter_documents(self, project_id: object) -> AsyncIterator[tuple[str, str]]:
        for path, content in self._docs:
            yield path, content


class FakeFiles:
    async def iter_files(
        self, project_id: object
    ) -> AsyncIterator[tuple[str, AsyncIterator[bytes]]]:
        return
        yield  # pragma: no cover


class FakeRunner:
    def __init__(self, outcome: RunOutcome, writes: dict[str, bytes] | None = None) -> None:
        self._outcome = outcome
        self._writes = writes or {}
        self.calls = 0

    async def run(self, *, output_dir: Path, **_kw: object) -> RunOutcome:
        self.calls += 1
        for rel, data in self._writes.items():
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return self._outcome


def ok_outcome(exit_code: int = 0) -> RunOutcome:
    return RunOutcome(
        exit_code=exit_code,
        stdout="out",
        stderr="err",
        timed_out=False,
        cancelled=False,
        duration_ms=12,
    )


def build_service(
    tmp_path: Path, runner: FakeRunner, docs: list[tuple[str, str]], **over: object
) -> CompileService:
    settings = make_settings(tmp_path, **over)
    return CompileService(
        settings=settings,
        runner=runner,
        docs=FakeDocs(docs),
        files=FakeFiles(),
        packages=load_package_config(tmp_path / "none.toml", settings),
    )


async def test_success_returns_pdf(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF-1.7", "main.log": b"This is the log"})
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.status is CompileStatus.SUCCESS
    assert result.pdf is not None
    assert result.pdf.content_type == "application/pdf"
    assert "This is the log" in result.log_text


async def test_latex_error_is_failure(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(exit_code=1), {"main.log": b"! Undefined control sequence"})
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.status is CompileStatus.FAILURE
    assert result.pdf is None
    assert "Undefined control sequence" in result.log_text
    assert result.stderr == "err"


async def test_timeout_outcome(tmp_path: Path) -> None:
    runner = FakeRunner(
        RunOutcome(
            exit_code=None, stdout="", stderr="", timed_out=True, cancelled=False, duration_ms=1
        )
    )
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.status is CompileStatus.TIMEOUT


async def test_cancelled_before_run(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome())
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    token = CancelToken()
    token.cancel()
    result = await service.compile(CompileOptions(project_id=uuid4()), cancel=token)
    assert result.status is CompileStatus.CANCELLED
    assert runner.calls == 0


async def test_cleanup_default_removes_workdir(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF"})
    cid = uuid4()
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    await service.compile(CompileOptions(project_id=uuid4(), compile_id=cid))
    assert not (tmp_path / str(cid)).exists()


async def test_keep_workdir_retains_and_reports(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF"})
    cid = uuid4()
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(
        CompileOptions(project_id=uuid4(), compile_id=cid, keep_workdir=True)
    )
    assert (tmp_path / str(cid)).exists()
    assert result.workdir == tmp_path / str(cid)


async def test_input_limit_short_circuits_before_runner(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome())
    service = build_service(
        tmp_path, runner, [("a.tex", "a"), ("b.tex", "b")], compile_max_input_files=1
    )
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.status is CompileStatus.SYSTEM_ERROR
    assert runner.calls == 0


async def test_traversal_path_is_system_error(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome())
    service = build_service(tmp_path, runner, [("../../etc/passwd", "x")])
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.status is CompileStatus.SYSTEM_ERROR
    assert runner.calls == 0


async def test_missing_main_file_is_failure(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome())
    service = build_service(tmp_path, runner, [("other.tex", "x")])
    result = await service.compile(CompileOptions(project_id=uuid4(), main_file="main.tex"))
    assert result.status is CompileStatus.FAILURE
    assert "root document not found" in result.log_text
    assert runner.calls == 0


async def test_log_truncation_sets_flag(tmp_path: Path) -> None:
    big = b"L" * 5000
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF", "main.log": big})
    service = build_service(tmp_path, runner, [("main.tex", "hi")], compile_max_log_bytes=100)
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.truncated is True
    assert len(result.log_text) == 100
