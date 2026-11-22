"""COMPILE_SANDBOX_MEMORY_MB takes effect unless COMPILE_ADDRESS_SPACE_BYTES is set explicitly.

The address space defaults to 2 GiB, the same as the sandbox memory cap. It is derived from
the memory cap when left at its default, so the container's --memory follows the cap.
"""

from __future__ import annotations

from inkstave.core.config.settings import Settings
from inkstave.modules.compile.running.limits import ResourceLimits
from inkstave.modules.compile.running.sandbox import SandboxCaps, SandboxedTectonicRunner

MIB = 1024 * 1024


def _memory_mb(settings: Settings) -> int:
    runner = SandboxedTectonicRunner(
        image="img",
        runtime="runc",
        docker_bin="docker",
        caps=SandboxCaps(memory_mb=settings.compile_sandbox_memory_mb),
        output_format="pdf",
    )
    limits = ResourceLimits(
        max_input_files=1,
        max_input_bytes=1,
        max_output_bytes=1,
        max_log_bytes=1,
        max_stdout_bytes=1,
        cpu_seconds=None,
        address_space_bytes=settings.compile_address_space_bytes,
    )
    return runner._memory_for(limits)


def test_default_address_space_is_derived_from_the_sandbox_memory_cap() -> None:
    settings = Settings(compile_sandbox_memory_mb=4096)
    assert settings.compile_address_space_bytes == 4096 * MIB
    assert _memory_mb(settings) == 4096


def test_default_memory_cap_keeps_the_two_gib_address_space() -> None:
    settings = Settings()
    assert settings.compile_address_space_bytes == 2048 * MIB
    assert _memory_mb(settings) == 2048


def test_explicit_address_space_wins_over_the_memory_cap() -> None:
    settings = Settings(compile_sandbox_memory_mb=4096, compile_address_space_bytes=1024 * MIB)
    assert settings.compile_address_space_bytes == 1024 * MIB
    assert _memory_mb(settings) == 1024


def test_empty_address_space_disables_it_and_the_memory_cap_applies() -> None:
    settings = Settings(compile_sandbox_memory_mb=512, compile_address_space_bytes=None)
    assert settings.compile_address_space_bytes is None
    assert _memory_mb(settings) == 512
