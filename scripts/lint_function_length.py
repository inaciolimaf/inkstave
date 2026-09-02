#!/usr/bin/env python3
"""Fail when a function body exceeds the project's line ceiling.

Ruff has no "function too long" rule (PLR0915 counts *statements*, not lines),
so this dependency-free AST check fills the gap. It is wired into `just lint`
and the pre-commit hooks; see docs/adr/0106-complexity-and-security-lint.md for the rationale
behind the ceiling.

Counted: every physical line of the function body that carries code.
Not counted: the `def`/decorator header, blank lines, comment-only lines, and
the docstring — documenting a function must never push it over the limit.

    scripts/lint_function_length.py [--max N] [PATH ...]
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from pathlib import Path

DEFAULT_MAX_LINES = 30
DEFAULT_PATHS = ("backend/src", "backend/tests", "backend/scripts", "scripts")
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
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        if isinstance(first.value.value, str):
            return (first.end_lineno or first.lineno) + 1
    return first.lineno


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


def check_file(path: Path, max_lines: int) -> list[str]:
    """Return one message per over-long function in `path`."""
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
                f"{path}:{node.lineno}: {node.name}() is {length} lines "
                f"(max {max_lines}) — split it up"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=None)
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_LINES, dest="max_lines")
    args = parser.parse_args(argv)

    findings = []
    for path in iter_python_files(args.paths or list(DEFAULT_PATHS)):
        findings.extend(check_file(path, args.max_lines))

    for message in findings:
        print(message)
    if findings:
        print(f"\n{len(findings)} function(s) over the {args.max_lines}-line ceiling.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
