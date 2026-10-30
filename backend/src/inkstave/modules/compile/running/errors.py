"""Compile-specific exceptions (spec 21)."""

from __future__ import annotations


class CompileError(Exception):
    """Base for compile-service errors mapped to ``SYSTEM_ERROR``."""


class UnsafePathError(CompileError):
    """A document/file path escaped the workdir (absolute, ``..``, or symlink)."""


class InputLimitError(CompileError):
    """Assembled inputs exceeded the configured file-count or byte limits."""
