#!/usr/bin/env python3
"""Fail when a function body or a whole file exceeds the project's line ceilings.

Ruff has no "function too long" rule (PLR0915 counts *statements*, not lines),
so this dependency-free AST check fills the gap. It is wired into `make lint`
and the pre-commit hooks; see docs/adr/0106-complexity-and-security-lint.md for the rationale
behind the ceiling.

Counted: every physical line that carries code.
Not counted: the `def`/decorator header (for a function), blank lines, comment-only
lines, and docstrings — documenting code must never push it over the limit.

    scripts/lint_function_length.py [--max N] [--max-file-lines N] [PATH ...]
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from pathlib import Path

DEFAULT_MAX_LINES = 30
DEFAULT_MAX_FILE_LINES = 300
DEFAULT_PATHS = ("backend/src", "backend/tests", "backend/scripts", "scripts", "tools")
# Vendored / generated trees the ceiling does not apply to.
EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        ".git",
        "node_modules",
        "migrations",
    }
)

FunctionDef = ast.FunctionDef | ast.AsyncFunctionDef


def iter_python_files(paths: list[str]) -> Iterator[Path]:
    """Yield every .py file under `paths`, skipping vendored/generated trees."""
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
            continue
        for candidate in sorted(path.rglob("*.py")):
            if EXCLUDED_DIRS.isdisjoint(candidate.parts):
                yield candidate


def body_start(node: FunctionDef) -> int:
    """First line of the body, skipping a leading docstring."""
    first = node.body[0]
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    return (first.end_lineno or first.lineno) + 1 if is_docstring else first.lineno


def count_body_lines(node: FunctionDef, source_lines: list[str]) -> int:
    """Count the body's code-bearing physical lines."""
    start = body_start(node)
    end = node.end_lineno or start
    total = 0
    for lineno in range(start, end + 1):
        stripped = source_lines[lineno - 1].strip()
        if stripped and not stripped.startswith("#"):
            total += 1
    return total


def docstring_lines(tree: ast.Module) -> set[int]:
    """The physical lines taken by the docstrings of `tree`."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | FunctionDef):
            continue
        first = node.body[0] if node.body else None
        is_docstring = (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        )
        if first is not None and is_docstring:
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def count_file_lines(tree: ast.Module, source_lines: list[str]) -> int:
    """Count the file's code-bearing physical lines."""
    docstrings = docstring_lines(tree)
    total = 0
    for lineno, line in enumerate(source_lines, start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and lineno not in docstrings:
            total += 1
    return total


def check_file(path: Path, max_lines: int, max_file_lines: int = DEFAULT_MAX_FILE_LINES) -> list[str]:
    """Return one message per over-long function in `path`, plus one if the file is."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - unparsable file
        return [f"{path}:{exc.lineno}: syntax error: {exc.msg}"]
    source_lines = source.splitlines()
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        length = count_body_lines(node, source_lines)
        if length > max_lines:
            findings.append(
                f"{path}:{node.lineno}: {node.name}() is {length} lines (max {max_lines}) — split it up"
            )
    file_length = count_file_lines(tree, source_lines)
    if file_length > max_file_lines:
        findings.append(
            f"{path}:1: the file has {file_length} useful lines "
            f"(max {max_file_lines}) — split it by responsibility"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=None)
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_LINES, dest="max_lines")
    parser.add_argument("--max-file-lines", type=int, default=DEFAULT_MAX_FILE_LINES)
    args = parser.parse_args(argv)

    findings = []
    for path in iter_python_files(args.paths or list(DEFAULT_PATHS)):
        findings.extend(check_file(path, args.max_lines, args.max_file_lines))

    for message in findings:
        print(message)
    if findings:
        print(f"\n{len(findings)} finding(s) over the size ceilings.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
