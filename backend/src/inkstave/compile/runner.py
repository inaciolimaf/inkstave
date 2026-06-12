"""Tectonic runner: an injectable protocol + the real subprocess implementation (spec 21)."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.result import RunOutcome


class TectonicRunner(Protocol):
    async def run(
        self,
        *,
        workdir: Path,
        main_file: str,
        output_dir: Path,
        timeout_s: int,
        limits: ResourceLimits,
        cancel: CancelToken,
    ) -> RunOutcome: ...


@dataclass(slots=True)
class TectonicCommand:
    argv: list[str]
    env: dict[str, str]


def _cap(data: bytes, limit: int) -> str:
    return data[:limit].decode("utf-8", "replace")


def _rlimit_preexec(limits: ResourceLimits) -> Callable[[], None] | None:
    if os.name != "posix":
        return None
    if limits.cpu_seconds is None and limits.address_space_bytes is None:
        return None

    def _apply() -> None:  # pragma: no cover - runs in the forked child
        import resource

        if limits.cpu_seconds is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
        if limits.address_space_bytes is not None:
            resource.setrlimit(
                resource.RLIMIT_AS, (limits.address_space_bytes, limits.address_space_bytes)
            )

    return _apply


class LocalTectonicRunner:
    """Runs the real ``tectonic`` binary via ``asyncio.create_subprocess_exec`` (no shell)."""

    def __init__(
        self,
        *,
        bin_path: str,
        cache_dir: Path,
        bundle_url: str | None,
        offline: bool,
        output_format: str = "latex",
    ) -> None:
        self._bin = bin_path
        self._cache_dir = cache_dir
        self._bundle_url = bundle_url
        self._offline = offline
        self._format = output_format

    def build_command(self, *, main_file: str, output_dir: Path) -> TectonicCommand:
        """The non-executing seam: build the argv + env (asserted by tests)."""
        argv = [
            self._bin,
            "-X",
            "compile",
            main_file,
            "--outdir",
            str(output_dir),
            "--outfmt",
            "pdf",
            "--synctex",
            "--keep-logs",
            "--keep-intermediates",
        ]
        if self._offline:
            argv.append("--only-cached")
        if self._bundle_url:
            argv += ["--bundle", self._bundle_url]
        env = {**os.environ, "TECTONIC_CACHE_DIR": str(self._cache_dir)}
        return TectonicCommand(argv=argv, env=env)

    async def run(
        self,
        *,
        workdir: Path,
        main_file: str,
        output_dir: Path,
        timeout_s: int,
        limits: ResourceLimits,
        cancel: CancelToken,
    ) -> RunOutcome:
        command = self.build_command(main_file=main_file, output_dir=output_dir)
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *command.argv,
            cwd=str(workdir / "input"),
            env=command.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=_rlimit_preexec(limits),
        )

        comm = asyncio.ensure_future(proc.communicate())
        cancel_wait = asyncio.ensure_future(cancel.wait())
        done, _pending = await asyncio.wait(
            {comm, cancel_wait}, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if comm in done and not cancel_wait.done():
            cancel_wait.cancel()
            stdout, stderr = comm.result()
            return RunOutcome(
                exit_code=proc.returncode,
                stdout=_cap(stdout, limits.max_stdout_bytes),
                stderr=_cap(stderr, limits.max_stdout_bytes),
                timed_out=False,
                cancelled=False,
                duration_ms=duration_ms,
            )

        cancelled = cancel_wait.done()
        await self._terminate(proc)
        cancel_wait.cancel()
        try:
            stdout, stderr = await comm
        except Exception:  # pragma: no cover - defensive
            stdout, stderr = b"", b""
        return RunOutcome(
            exit_code=proc.returncode,
            stdout=_cap(stdout, limits.max_stdout_bytes),
            stderr=_cap(stderr, limits.max_stdout_bytes),
            timed_out=not cancelled,
            cancelled=cancelled,
            duration_ms=duration_ms,
        )

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (TimeoutError, asyncio.TimeoutError):  # noqa: UP041
            proc.kill()
            await proc.wait()
