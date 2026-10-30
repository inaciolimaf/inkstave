"""Tectonic runner: an injectable protocol + the real subprocess implementation (spec 21)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inkstave.modules.compile.running.limits import CancelToken, ResourceLimits
from inkstave.modules.compile.running.result import RunOutcome

logger = logging.getLogger(__name__)


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
            resource.setrlimit(resource.RLIMIT_AS, (limits.address_space_bytes, limits.address_space_bytes))

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
        # Minimal, allow-listed environment (spec 52 §5.4): do NOT inherit the full
        # process env, so application secrets (JWT_SECRET, OPENROUTER_API_KEY, DB/Redis
        # creds) are never exposed to a LaTeX compile. Tectonic has no shell-escape, so
        # \write18 is disabled by design.
        passthrough = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
        env = {k: os.environ[k] for k in passthrough if k in os.environ}
        env["TECTONIC_CACHE_DIR"] = str(self._cache_dir)
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
        watch = ProcessWatch(proc, limits, start)
        outcome = await watch.wait(cancel, timeout_s)
        if outcome is not None:
            return outcome
        await self._terminate(proc)
        return await watch.reap()

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()


class ProcessWatch:
    """Waits on a compile subprocess with both a timeout and a cancel token.

    Both runners share this: a clean finish yields the outcome directly, while a
    timeout or a cancel makes `wait()` return ``None`` so the caller can kill the
    process its own way before `reap()` collects whatever it produced.
    """

    def __init__(self, proc: asyncio.subprocess.Process, limits: ResourceLimits, start: float) -> None:
        self._proc = proc
        self._limits = limits
        self._start = start
        self._comm = asyncio.ensure_future(proc.communicate())
        self._cancel_wait: asyncio.Future[None] | None = None
        self._duration_ms = 0
        self._cancelled = False

    async def wait(self, cancel: CancelToken, timeout_s: int) -> RunOutcome | None:
        """The outcome of a clean finish, or ``None`` on timeout / cancellation."""
        self._cancel_wait = asyncio.ensure_future(cancel.wait())
        done, _pending = await asyncio.wait(
            {self._comm, self._cancel_wait},
            timeout=timeout_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        self._duration_ms = int((time.monotonic() - self._start) * 1000)
        if self._comm in done and not self._cancel_wait.done():
            self._cancel_wait.cancel()
            stdout, stderr = self._comm.result()
            return self._outcome(stdout, stderr, timed_out=False, cancelled=False)
        self._cancelled = self._cancel_wait.done()
        return None

    async def reap(self) -> RunOutcome:
        """Collect whatever the terminated process produced."""
        if self._cancel_wait is not None:
            self._cancel_wait.cancel()
        try:
            stdout, stderr = await self._comm
        except Exception:  # pragma: no cover - defensive
            stdout, stderr = b"", b""
        return self._outcome(stdout, stderr, timed_out=not self._cancelled, cancelled=self._cancelled)

    def _outcome(self, stdout: bytes, stderr: bytes, *, timed_out: bool, cancelled: bool) -> RunOutcome:
        return RunOutcome(
            exit_code=self._proc.returncode,
            stdout=_cap(stdout, self._limits.max_stdout_bytes),
            stderr=_cap(stderr, self._limits.max_stdout_bytes),
            timed_out=timed_out,
            cancelled=cancelled,
            duration_ms=self._duration_ms,
        )
