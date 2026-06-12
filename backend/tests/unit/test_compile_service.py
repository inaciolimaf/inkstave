"""Unit tests for CompileService orchestration with a fake runner (spec 21)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

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
        self.main_file: object = None

    async def run(self, *, output_dir: Path, **_kw: object) -> RunOutcome:
        self.calls += 1
        self.main_file = _kw.get("main_file")
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


async def test_cancelled_while_running_maps_to_cancelled(tmp_path: Path) -> None:
    # AC4 / spec 68 #75: a token cancelled *while the runner is running* (the runner
    # is actually invoked and returns RunOutcome(cancelled=True)) must map to
    # CANCELLED via _build_result — distinct from test_cancelled_before_run, which
    # short-circuits with runner.calls == 0.
    outcome = RunOutcome(
        exit_code=None, stdout="", stderr="", timed_out=False, cancelled=True, duration_ms=7
    )
    runner = FakeRunner(outcome)
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert runner.calls == 1  # the runner ran (not a pre-run short-circuit)
    assert result.status is CompileStatus.CANCELLED


async def test_cleanup_default_removes_workdir(tmp_path: Path) -> None:
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF"})
    cid = uuid4()
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    await service.compile(CompileOptions(project_id=uuid4(), compile_id=cid))
    assert not (tmp_path / str(cid)).exists()


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            RunOutcome(
                exit_code=1, stdout="", stderr="", timed_out=False, cancelled=False, duration_ms=3
            ),
            CompileStatus.FAILURE,
        ),
        (
            RunOutcome(
                exit_code=None, stdout="", stderr="", timed_out=True, cancelled=False, duration_ms=3
            ),
            CompileStatus.TIMEOUT,
        ),
        (
            RunOutcome(
                exit_code=None, stdout="", stderr="", timed_out=False, cancelled=True, duration_ms=3
            ),
            CompileStatus.CANCELLED,
        ),
    ],
)
async def test_cleanup_removes_workdir_on_non_success(
    tmp_path: Path, outcome: RunOutcome, expected: CompileStatus
) -> None:
    # AC5 / spec 68 #76: for *any* terminal outcome, with keep_workdir=False, the
    # finally-block cleanup leaves no workdir on disk — not only the success path.
    runner = FakeRunner(outcome)
    cid = uuid4()
    service = build_service(tmp_path, runner, [("main.tex", "hi")])
    result = await service.compile(CompileOptions(project_id=uuid4(), compile_id=cid))
    assert result.status is expected
    assert not (tmp_path / str(cid)).exists()


async def test_cleanup_removes_workdir_on_system_error(tmp_path: Path) -> None:
    # SYSTEM_ERROR path (spec 68 #76): the workdir is created before assemble fails,
    # and the finally block must still remove it.
    runner = FakeRunner(ok_outcome())
    cid = uuid4()
    service = build_service(tmp_path, runner, [("../../etc/passwd", "x")])
    result = await service.compile(CompileOptions(project_id=uuid4(), compile_id=cid))
    assert result.status is CompileStatus.SYSTEM_ERROR
    assert runner.calls == 0
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


async def test_missing_main_file_falls_back_to_first_tex(tmp_path: Path) -> None:
    # No main.tex, but the project has a .tex: compile it instead of failing. The
    # runner must emit a PDF for the result to be SUCCESS (exit 0 alone is not enough).
    runner = FakeRunner(ok_outcome(), {"other.pdf": b"%PDF-1.7"})
    service = build_service(tmp_path, runner, [("other.tex", "x")])
    result = await service.compile(CompileOptions(project_id=uuid4(), main_file="main.tex"))
    assert result.status is CompileStatus.SUCCESS
    assert runner.calls == 1
    assert runner.main_file == "other.tex"


async def test_fallback_prefers_documentclass_root(tmp_path: Path) -> None:
    # Among several .tex files, prefer the one declaring \documentclass.
    runner = FakeRunner(ok_outcome())
    service = build_service(
        tmp_path,
        runner,
        [("aaa.tex", "% just notes"), ("paper.tex", "\\documentclass{article}\n\\end{document}")],
    )
    await service.compile(CompileOptions(project_id=uuid4(), main_file="main.tex"))
    assert runner.main_file == "paper.tex"


async def test_no_tex_file_is_failure(tmp_path: Path) -> None:
    # Nothing to compile at all → a clear failure, runner never invoked.
    runner = FakeRunner(ok_outcome())
    service = build_service(tmp_path, runner, [("notes.txt", "hello")])
    result = await service.compile(CompileOptions(project_id=uuid4(), main_file="main.tex"))
    assert result.status is CompileStatus.FAILURE
    assert "no .tex file" in result.log_text
    assert runner.calls == 0


async def test_log_truncation_sets_flag(tmp_path: Path) -> None:
    big = b"L" * 5000
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF", "main.log": big})
    service = build_service(tmp_path, runner, [("main.tex", "hi")], compile_max_log_bytes=100)
    result = await service.compile(CompileOptions(project_id=uuid4()))
    assert result.truncated is True
    assert len(result.log_text) == 100
