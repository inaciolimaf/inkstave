"""Sandboxed Tectonic: every compile in a throwaway gVisor container (spec 105)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from inkstave.compile.errors import CompileError
from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.result import RunOutcome
from inkstave.compile.runner import LocalTectonicRunner, ProcessWatch

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True)
class SandboxCaps:
    """Hard resource caps of the throwaway compile container."""

    memory_mb: int = 2048
    cpus: float = 1.0
    pids_limit: int = 256
    tmpfs_mb: int = 256


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
        caps: SandboxCaps | None = None,
        output_format: str = "latex",
    ) -> None:
        self._image = image
        self._runtime = runtime
        self._docker_bin = docker_bin
        self._caps = caps or SandboxCaps()
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
        return self._caps.memory_mb

    def _sandbox_flags(self, limits: ResourceLimits, container_name: str) -> list[str]:
        """The fixed hardening flags for the throwaway compile container."""
        return [
            f"--runtime={self._runtime}",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            # Not a host path: `/tmp` here is the tmpfs mount point *inside* the
            # throwaway container, which has no writable filesystem otherwise.
            f"/tmp:size={self._caps.tmpfs_mb}m",  # noqa: S108 — see above
            "--user",
            "65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self._caps.pids_limit),
            "--memory",
            f"{self._memory_for(limits)}m",
            "--cpus",
            str(self._caps.cpus),
            "--name",
            container_name,
        ]

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
            *self._sandbox_flags(limits, container_name),
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
        watch = ProcessWatch(proc, limits, start)
        outcome = await watch.wait(cancel, timeout_s)
        if outcome is not None:
            return outcome

        # On timeout/cancel, kill the container by name (it outlives the SIGTERM'd
        # launcher otherwise), then reap the launcher process.
        await self._kill_container(container_name)
        await LocalTectonicRunner._terminate(proc)
        return await watch.reap()

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
            logger.debug("docker kill failed for %s", container_name, exc_info=True)
