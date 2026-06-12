"""The synchronous compile service — assemble, run Tectonic, map the result (spec 21)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from inkstave.compile.errors import CompileError
from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.result import CompileResult, CompileStatus, RunOutcome
from inkstave.compile.workdir import (
    assemble_inputs,
    cleanup_workdir,
    collect_outputs,
    create_workdir,
)

if TYPE_CHECKING:
    from inkstave.compile.packages import PackageConfig
    from inkstave.compile.runner import TectonicRunner
    from inkstave.compile.workdir import DocumentSource, FileSource
    from inkstave.config import Settings

_FAILED = {CompileStatus.FAILURE, CompileStatus.TIMEOUT, CompileStatus.SYSTEM_ERROR}


@dataclass(slots=True)
class CompileOptions:
    project_id: UUID
    main_file: str = "main.tex"
    timeout_s: int | None = None
    keep_workdir: bool = False
    compile_id: UUID | None = None


class CompileService:
    def __init__(
        self,
        *,
        settings: Settings,
        runner: TectonicRunner,
        docs: DocumentSource,
        files: FileSource,
        packages: PackageConfig,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._docs = docs
        self._files = files
        self._packages = packages

    def _limits(self) -> ResourceLimits:
        s = self._settings
        return ResourceLimits(
            max_input_files=s.compile_max_input_files,
            max_input_bytes=s.compile_max_input_bytes,
            max_output_bytes=s.compile_max_output_bytes,
            max_log_bytes=s.compile_max_log_bytes,
            max_stdout_bytes=s.compile_max_stdout_bytes,
            cpu_seconds=s.compile_cpu_seconds,
            address_space_bytes=s.compile_address_space_bytes,
        )

    async def compile(
        self, opts: CompileOptions, cancel: CancelToken | None = None
    ) -> CompileResult:
        cancel = cancel or CancelToken()
        limits = self._limits()
        timeout_s = opts.timeout_s or self._settings.tectonic_compile_timeout_s
        compile_id = opts.compile_id or uuid4()
        workdir: Path | None = None
        result: CompileResult | None = None

        try:
            workdir = await create_workdir(Path(self._settings.compile_workdir_root), compile_id)

            if cancel.is_cancelled:
                result = _empty(CompileStatus.CANCELLED)
                return result

            try:
                await assemble_inputs(
                    workdir=workdir,
                    project_id=opts.project_id,
                    docs=self._docs,
                    files=self._files,
                    limits=limits,
                )
            except CompileError as exc:
                result = _empty(CompileStatus.SYSTEM_ERROR, log_text=str(exc))
                return result

            if not (workdir / "input" / opts.main_file).is_file():
                result = _empty(
                    CompileStatus.FAILURE, log_text=f"root document not found: {opts.main_file}"
                )
                return result

            if cancel.is_cancelled:
                result = _empty(CompileStatus.CANCELLED)
                return result

            outcome = await self._runner.run(
                workdir=workdir,
                main_file=opts.main_file,
                output_dir=workdir / "output",
                timeout_s=timeout_s,
                limits=limits,
                cancel=cancel,
            )
            result = self._build_result(workdir, opts.main_file, outcome, limits)
            return result
        except Exception as exc:  # pragma: no cover - defensive catch-all
            result = _empty(CompileStatus.SYSTEM_ERROR, log_text=f"compile failed: {exc}")
            return result
        finally:
            if workdir is not None:
                keep = opts.keep_workdir or (
                    result is not None
                    and result.status in _FAILED
                    and self._settings.compile_keep_workdir_on_failure
                )
                if keep:
                    if result is not None:
                        result.workdir = workdir
                else:
                    await cleanup_workdir(workdir)

    def _build_result(
        self, workdir: Path, main_file: str, outcome: RunOutcome, limits: ResourceLimits
    ) -> CompileResult:
        output_dir = workdir / "output"
        artifacts = collect_outputs(output_dir)
        pdf = next((a for a in artifacts if a.content_type == "application/pdf"), None)
        log_text, truncated = self._read_log(output_dir, main_file, outcome, limits)

        if outcome.cancelled:
            status = CompileStatus.CANCELLED
        elif outcome.timed_out:
            status = CompileStatus.TIMEOUT
        elif outcome.exit_code == 0 and pdf is not None:
            status = CompileStatus.SUCCESS
        else:
            status = CompileStatus.FAILURE

        return CompileResult(
            status=status,
            pdf=pdf if status == CompileStatus.SUCCESS else None,
            log_text=log_text,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            exit_code=outcome.exit_code,
            duration_ms=outcome.duration_ms,
            artifacts=artifacts,
            truncated=truncated,
        )

    @staticmethod
    def _read_log(
        output_dir: Path, main_file: str, outcome: RunOutcome, limits: ResourceLimits
    ) -> tuple[str, bool]:
        log_path = output_dir / f"{Path(main_file).stem}.log"
        if log_path.is_file():
            raw = log_path.read_bytes()
        else:
            raw = outcome.stdout.encode("utf-8")
        truncated = len(raw) > limits.max_log_bytes
        return raw[: limits.max_log_bytes].decode("utf-8", "replace"), truncated


def _empty(status: CompileStatus, *, log_text: str = "") -> CompileResult:
    return CompileResult(
        status=status,
        pdf=None,
        log_text=log_text,
        stdout="",
        stderr="",
        exit_code=None,
        duration_ms=0,
    )
