"""scripts/lint_function_length.py: the function and file ceilings."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "lint_function_length.py"
_spec = importlib.util.spec_from_file_location("lint_function_length", _SCRIPT)
assert _spec is not None and _spec.loader is not None
size_lint = importlib.util.module_from_spec(_spec)
sys.modules["lint_function_length"] = size_lint
_spec.loader.exec_module(size_lint)


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_file_over_the_ceiling_is_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, "".join(f"a{i} = {i}\n" for i in range(5)))
    assert len(size_lint.check_file(path, 30, 4)) == 1
    assert size_lint.check_file(path, 30, 5) == []


def test_blank_lines_comments_and_docstrings_do_not_count(tmp_path: Path) -> None:
    source = '"""Module\ndocstring."""\n\n# comment\n\ndef f() -> None:\n    """Doc."""\n    return\n'
    assert size_lint.check_file(_write(tmp_path, source), 30, 2) == []


def test_function_ceiling_still_applies(tmp_path: Path) -> None:
    body = "".join(f"    a{i} = {i}\n" for i in range(4))
    findings = size_lint.check_file(_write(tmp_path, f"def f() -> None:\n{body}"), 3)
    assert len(findings) == 1
    assert "f() is 4 lines" in findings[0]
