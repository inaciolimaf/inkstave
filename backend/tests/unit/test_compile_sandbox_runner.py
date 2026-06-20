"""Unit tests for SandboxedTectonicRunner argv construction + the run() kill path.

No real container is ever spawned (spec 105): the build_command seam is asserted
directly, and run()'s timeout/cancel path is exercised with a fake subprocess.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from inkstave.compile.errors import CompileError
from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.runner import SandboxedTectonicRunner, validate_main_file


def _limits(*, address_space_bytes: int | None = 2_147_483_648) -> ResourceLimits:
    return ResourceLimits(
        max_input_files=2000,
        max_input_bytes=104_857_600,
        max_output_bytes=104_857_600,
        max_log_bytes=2_097_152,
        max_stdout_bytes=262_144,
        cpu_seconds=60,
        address_space_bytes=address_space_bytes,
    )


def _runner(**kwargs: Any) -> SandboxedTectonicRunner:
    return SandboxedTectonicRunner(image="inkstave-tectonic", **kwargs)


def _cmd(main_file: str = "main.tex", **kwargs: Any) -> Any:
    return _runner(**kwargs).build_command(
        workdir=Path("/wd"),
        main_file=main_file,
        output_dir=Path("/wd/output"),
        limits=_limits(),
        container_name="inkstave-compile-test",
    )


def test_docker_argv_carries_the_isolation_flags() -> None:
    argv = _cmd().argv
    assert argv[0] == "docker"
    assert argv[1] == "run"
    assert "--rm" in argv
    assert "--runtime=runsc" in argv
    # --network none, --cap-drop ALL etc. are flag/value pairs.
    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert argv[argv.index("--user") + 1] == "65534"
    assert "--read-only" in argv
    assert argv[argv.index("--name") + 1] == "inkstave-compile-test"


def test_resource_caps_map_to_container_flags() -> None:
    argv = _cmd(pids_limit=128, cpus=2.0, tmpfs_mb=64).argv
    # --memory derives from address_space_bytes (2 GiB -> 2048m).
    assert argv[argv.index("--memory") + 1] == "2048m"
    assert argv[argv.index("--pids-limit") + 1] == "128"
    assert argv[argv.index("--cpus") + 1] == "2.0"
    assert argv[argv.index("--tmpfs") + 1] == "/tmp:size=64m"


def test_memory_falls_back_to_setting_when_address_space_unset() -> None:
    runner = _runner(memory_mb=512)
    cmd = runner.build_command(
        workdir=Path("/wd"),
        main_file="main.tex",
        output_dir=Path("/wd/output"),
        limits=_limits(address_space_bytes=None),
        container_name="c",
    )
    assert cmd.argv[cmd.argv.index("--memory") + 1] == "512m"


def test_mounts_are_read_only_input_and_writable_output() -> None:
    argv = _cmd().argv
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert "/wd/input:/work:ro" in mounts
    assert "/wd/output:/out" in mounts
    # The image name comes after all flags and before the inner tectonic argv.
    img = argv.index("inkstave-tectonic")
    assert argv[img + 1] == "tectonic"


def test_inner_tectonic_argv_targets_out_and_is_offline() -> None:
    argv = _cmd().argv
    assert "compile" in argv
    assert argv[argv.index("--outdir") + 1] == "/out"
    assert "--only-cached" in argv  # the sandbox image is offline


def test_no_secrets_or_extra_user_data_in_argv_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mirror test_compile_sandbox_no_shell_escape_no_inherited_secrets (spec 52):
    # application secrets must never reach the docker argv or the launcher env.
    monkeypatch.setenv("JWT_SECRET", "super-secret-value")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-leak")
    cmd = _cmd(main_file="report.tex")
    blob = " ".join(cmd.argv) + " " + " ".join(cmd.env.values())
    assert "super-secret-value" not in blob
    assert "sk-leak" not in blob
    assert "JWT_SECRET" not in cmd.env and "OPENROUTER_API_KEY" not in cmd.env
    assert set(cmd.env) <= {"PATH", "HOME"}
    # The only user-derived token in the argv is the validated main file.
    assert "report.tex" in cmd.argv


@pytest.mark.parametrize(
    "bad",
    [
        "/etc/passwd",  # absolute
        "../../etc/passwd",  # traversal
        "../secret.tex",
        "-oProxyCommand.tex",  # leading-dash / option injection
        "a/-x.tex",  # leading-dash segment
        "ma in.tex",  # whitespace
        "main;rm -rf.tex",  # shell metacharacters
        "main$(id).tex",
        "main\x00.tex",  # NUL
        "main\n.tex",  # control char
        "",  # empty
        "./main.tex",  # dot segment
    ],
)
def test_dangerous_main_files_are_rejected(bad: str) -> None:
    with pytest.raises(CompileError):
        validate_main_file(bad)
    # And the runner refuses to build a command for them (never spawns).
    with pytest.raises(CompileError):
        _cmd(main_file=bad)


def test_safe_nested_main_file_is_accepted() -> None:
    assert validate_main_file("chapters/intro.tex") == "chapters/intro.tex"
    argv = _cmd(main_file="chapters/intro.tex").argv
    assert "chapters/intro.tex" in argv


def test_username_like_string_never_leaks_into_argv() -> None:
    # The runner is given no usernames; assert a sentinel that would only appear if
    # some user identity were ever spliced into the command is absent.
    argv = _cmd(main_file="main.tex").argv
    assert not any("attacker@example.com" in a for a in argv)


class _FakeProc:
    """A stand-in for asyncio's subprocess: communicate() blocks until terminated."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self._done = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes]:
        await self._done.wait()
        return b"out", b"err"

    def terminate(self) -> None:
        self.returncode = -15
        self._done.set()

    def kill(self) -> None:  # pragma: no cover - terminate resolves first here
        self.returncode = -9
        self._done.set()

    async def wait(self) -> int | None:
        await self._done.wait()
        return self.returncode


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, calls: list[list[str]]) -> _FakeProc:
    run_proc = _FakeProc()

    async def fake_exec(*argv: str, **_kwargs: Any) -> Any:
        calls.append(list(argv))
        if "kill" in argv:
            # The docker-kill side-process: a finished proc.
            killer = _FakeProc()
            killer.terminate()
            return killer
        return run_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return run_proc


async def test_cancel_kills_the_container_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _patch_subprocess(monkeypatch, calls)
    cancel = CancelToken()
    cancel.cancel()  # already cancelled → the cancel branch fires deterministically
    outcome = await _runner().run(
        workdir=Path("/wd"),
        main_file="main.tex",
        output_dir=Path("/tmp/inkstave-sandbox-test-out"),
        timeout_s=30,
        limits=_limits(),
        cancel=cancel,
    )
    assert outcome.cancelled is True and outcome.timed_out is False
    kill_calls = [c for c in calls if "kill" in c]
    assert kill_calls, "expected a docker kill on cancel"
    assert kill_calls[0][1] == "kill" and kill_calls[0][2].startswith("inkstave-compile-")


async def test_timeout_kills_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    _patch_subprocess(monkeypatch, calls)
    outcome = await _runner().run(
        workdir=Path("/wd"),
        main_file="main.tex",
        output_dir=Path("/tmp/inkstave-sandbox-test-out"),
        timeout_s=0,  # immediate wall-clock timeout
        limits=_limits(),
        cancel=CancelToken(),
    )
    assert outcome.timed_out is True and outcome.cancelled is False
    assert any("kill" in c for c in calls), "expected a docker kill on timeout"
