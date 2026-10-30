"""Compile result/outcome types (spec 21). Pure dataclasses, no I/O."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


class CompileStatus(enum.StrEnum):
    SUCCESS = "success"  # PDF produced, exit code 0
    FAILURE = "failure"  # engine ran but produced no usable PDF
    TIMEOUT = "timeout"  # killed by the wall-clock limit
    CANCELLED = "cancelled"  # cooperatively cancelled before/while running
    SYSTEM_ERROR = "system_error"  # workdir/runner/IO failure unrelated to LaTeX


@dataclass(slots=True)
class CompileArtifact:
    name: str
    rel_path: str  # path relative to the workdir output root
    abs_path: Path
    size_bytes: int
    content_type: str


@dataclass(slots=True)
class RunOutcome:
    """What a :class:`TectonicRunner` reports back."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool
    duration_ms: int


@dataclass(slots=True)
class CompileResult:
    status: CompileStatus
    pdf: CompileArtifact | None
    log_text: str
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    artifacts: list[CompileArtifact] = field(default_factory=list)
    workdir: Path | None = None
    truncated: bool = False
