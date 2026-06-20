"""Tectonic runner: an injectable protocol + the real subprocess implementation (spec 21)."""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from inkstave.compile.errors import CompileError
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


@dataclass(slots=True)
class DockerCommand:
    """The fixed ``docker run`` argv + the ephemeral container name (asserted by tests)."""

    argv: list[str]
    container_name: str
    env: dict[str, str]


# A conservatively safe filename segment: must start alphanumeric (so it can
# never begin with ``-`` and be read as a docker/tectonic option) and otherwise
# allow only ``[A-Za-z0-9._+-]``. ``/`` is handled as the only path separator.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def validate_main_file(name: str) -> str:
    """Reject any ``main_file`` that could escape the mount or inject a docker/tectonic
    argument (spec 105 §5.2). Returns the name unchanged when safe, else raises
    ``CompileError`` so the compile is mapped to ``SYSTEM_ERROR`` without spawning."""
    if not name or name != name.strip():
        raise CompileError("invalid main file name")
    if "\x00" in name or any(ord(ch) < 0x20 for ch in name):
        raise CompileError("invalid characters in main file name")
    if PurePosixPath(name).is_absolute() or name.startswith("\\"):
        raise CompileError("main file must be a relative path")
    segments = name.split("/")
    for seg in segments:
        if seg in ("", ".", "..") or not _SAFE_SEGMENT.match(seg):
            raise CompileError(f"unsafe main file segment: {seg!r}")
    return name


class SandboxedTectonicRunner:
    """Runs each compile in an ephemeral, gVisor-isolated container (spec 105).

    The same ``tectonic … compile … --outdir /out`` argv as
    :class:`LocalTectonicRunner` runs **inside** a throwaway container with no
    network, a read-only root, all capabilities dropped, a non-root user and hard
    memory/PID/CPU/tmpfs caps enforced by the container engine (gVisor ``runsc``).
    The user's project is mounted read-only; nothing user-controlled ever reaches
    the ``docker`` argv (see :func:`validate_main_file`).
    """

    def __init__(
        self,
        *,
        image: str,
        runtime: str = "runsc",
        docker_bin: str = "docker",
        memory_mb: int = 2048,
        cpus: float = 1.0,
        pids_limit: int = 256,
        tmpfs_mb: int = 256,
        output_format: str = "latex",
    ) -> None:
        self._image = image
        self._runtime = runtime
        self._docker_bin = docker_bin
        self._memory_mb = memory_mb
        self._cpus = cpus
        self._pids_limit = pids_limit
        self._tmpfs_mb = tmpfs_mb
        # Reused only to build the inner tectonic argv; offline + cache live in the
        # image, so the bundle url / cache dir here are irrelevant to the container.
        self._inner = LocalTectonicRunner(
            bin_path="tectonic",
            cache_dir=Path("/var/cache/tectonic"),
            bundle_url=None,
            offline=True,
            output_format=output_format,
        )

    def _memory_for(self, limits: ResourceLimits) -> int:
        if limits.address_space_bytes is not None:
            return max(1, limits.address_space_bytes // (1024 * 1024))
        return self._memory_mb

    def build_command(
        self,
        *,
        workdir: Path,
        main_file: str,
        output_dir: Path,
        limits: ResourceLimits,
        container_name: str,
    ) -> DockerCommand:
        """The non-executing seam: assemble the fixed ``docker run`` argv (asserted by
        tests). No user data beyond the validated ``main_file`` and no secret env."""
        safe_main = validate_main_file(main_file)
        # Reuse the existing tectonic flag list; the container writes to /out and the
        # image carries the cache, so we keep only the argv (its env is discarded).
        inner = self._inner.build_command(main_file=safe_main, output_dir=Path("/out"))
        argv = [
            self._docker_bin,
            "run",
            "--rm",
            f"--runtime={self._runtime}",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            f"/tmp:size={self._tmpfs_mb}m",
            "--user",
            "65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self._pids_limit),
            "--memory",
            f"{self._memory_for(limits)}m",
            "--cpus",
            str(self._cpus),
            "--name",
            container_name,
            "--workdir",
            "/work",
            "-v",
            f"{workdir / 'input'}:/work:ro",
            "-v",
            f"{output_dir}:/out",
            self._image,
            *inner.argv,
        ]
        # Minimal env: only what's needed to resolve the docker binary. NEVER the
        # full process env, so application secrets cannot leak into the launcher.
        passthrough = ("PATH", "HOME")
        env = {k: os.environ[k] for k in passthrough if k in os.environ}
        return DockerCommand(argv=argv, container_name=container_name, env=env)

    @staticmethod
    def _container_name() -> str:
        return f"inkstave-compile-{uuid4().hex}"

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
        container_name = self._container_name()
        command = self.build_command(
            workdir=workdir,
            main_file=main_file,
            output_dir=output_dir,
            limits=limits,
            container_name=container_name,
        )
        # The bind-mount target must exist before docker, or the daemon creates it
        # root-owned; mkdir it here (the workdir is ours, never user-named).
        await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *command.argv,
            env=command.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        # On timeout/cancel, kill the container by name (it outlives the SIGTERM'd
        # launcher otherwise), then reap the launcher process.
        await self._kill_container(container_name)
        await LocalTectonicRunner._terminate(proc)
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

    async def _kill_container(self, container_name: str) -> None:
        try:
            killer = await asyncio.create_subprocess_exec(
                self._docker_bin,
                "kill",
                container_name,
                env={k: os.environ[k] for k in ("PATH", "HOME") if k in os.environ},
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=5.0)
        except Exception:  # pragma: no cover - best-effort; --rm reaps the container
            pass
