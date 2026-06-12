"""In-memory models for parsed LaTeX-log problems (spec 27)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ProblemSeverity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"  # typesetting (overfull/underfull) and recoverable notices


class Problem(BaseModel):
    severity: ProblemSeverity
    message: str  # cleaned, single-line summary
    file: str | None = None  # project-relative source path, None if unresolved
    line: int | None = None  # 1-based source line, None if unknown
    end_line: int | None = None  # for ranges (Overfull "lines a--b"); else None
    raw: str  # original log excerpt (a few lines) for the panel
    rule: str  # short machine id: "tex-error", "latex-warning", "overfull-hbox", …


class CompileProblems(BaseModel):
    compile_id: str
    errors: int
    warnings: int
    infos: int
    problems: list[Problem]
