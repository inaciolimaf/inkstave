"""Unit tests for diff computation (spec 43): pure, no DB."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstave.agent.diffs import is_oversized, is_stale
from inkstave.agent.diffs.compute import (
    DiffConflictError,
    apply_staged_edits,
    compute_diff,
    content_hash,
)
from inkstave.agent.edits import EditMode, StagedEdit


def _edit(mode: str, new_text: str, start: int | None = None, end: int | None = None) -> StagedEdit:
    return StagedEdit(
        edit_id="e",
        doc_id="d",
        path="f.tex",
        base_version="1",
        mode=EditMode(mode),
        new_text=new_text,
        start_line=start,
        end_line=end,
    )


# --- apply_staged_edits ---------------------------------------------------- #


def test_full_replacement() -> None:
    assert apply_staged_edits("old\ntext\n", [_edit("full", "brand\nnew\n")]) == "brand\nnew\n"


def test_single_range_replacement() -> None:
    out = apply_staged_edits("a\nb\nc\nd\n", [_edit("range", "B", start=1, end=2)])
    assert out == "a\nB\nc\nd\n"


def test_multiple_non_overlapping_ranges_applied_bottom_up() -> None:
    # AC3: replacing [1,2) and [3,4) must not drift indices.
    edits = [_edit("range", "X", start=1, end=2), _edit("range", "Y", start=3, end=4)]
    assert apply_staged_edits("a\nb\nc\nd\ne\n", edits) == "a\nX\nc\nY\ne\n"


def test_overlapping_ranges_raise_conflict() -> None:
    edits = [_edit("range", "X", start=1, end=3), _edit("range", "Y", start=2, end=4)]
    with pytest.raises(DiffConflictError):  # AC4
        apply_staged_edits("a\nb\nc\nd\ne\n", edits)


def test_full_wins_over_range() -> None:
    edits = [_edit("range", "X", start=0, end=1), _edit("full", "whole\n")]
    assert apply_staged_edits("a\nb\n", edits) == "whole\n"


def test_trailing_newline_preserved_and_absent() -> None:
    assert apply_staged_edits("a\nb", [_edit("range", "B", start=1, end=2)]) == "a\nB"
    assert apply_staged_edits("a\nb\n", [_edit("range", "B", start=1, end=2)]) == "a\nB\n"


# --- compute_diff ---------------------------------------------------------- #


def test_compute_diff_headers_and_ops() -> None:
    # AC1/AC8: 1-based headers, per-line ops, additions/deletions.
    current = "a\nb\nc\nd\ne\n"
    proposed = "a\nb\nC\nd\ne\n"  # replace line index 2 ("c") with "C"
    diff_text, hunks, stats = compute_diff(current, proposed, path="f.tex", context=3)

    assert diff_text.startswith("--- a/f.tex\n+++ b/f.tex\n@@ ")
    assert len(hunks) == 1
    h = hunks[0]
    assert h["hunk_id"] == "h1" and h["header"] == "@@ -1,5 +1,5 @@"
    assert h["old_start"] == 1 and h["old_lines"] == 5
    assert h["new_start"] == 1 and h["new_lines"] == 5
    assert h["additions"] == 1 and h["deletions"] == 1
    ops = [(line["op"], line["text"]) for line in h["lines"]]
    assert ("-", "c") in ops and ("+", "C") in ops and (" ", "a") in ops
    assert stats == {"additions": 1, "deletions": 1, "hunk_count": 1}


def test_no_op_diff_is_empty() -> None:
    diff_text, hunks, stats = compute_diff("same\n", "same\n", path="f.tex")
    assert diff_text == "" and hunks == [] and stats["hunk_count"] == 0  # AC5


def test_full_file_replacement_has_hunks() -> None:
    _diff, hunks, stats = compute_diff("a\nb\nc\n", "x\ny\nz\n", path="f.tex")
    assert stats["hunk_count"] >= 1 and hunks  # AC2


# --- drift ----------------------------------------------------------------- #


def test_is_stale_on_version_or_hash_change() -> None:
    diff = SimpleNamespace(base_version="3", base_hash=content_hash("abc"))
    assert is_stale(diff, "abc", 3) is False  # AC6: unchanged
    assert is_stale(diff, "abc", 4) is True  # version changed
    assert is_stale(diff, "abcX", 3) is True  # hash changed


# --- oversized-doc handling (AC9) ------------------------------------------ #


def test_is_oversized_skips_past_threshold() -> None:
    # AC9: a document strictly larger than the budget is skipped (the > branch).
    assert is_oversized("x" * 11, max_doc_chars=10) is True


def test_is_oversized_keeps_at_or_under_threshold() -> None:
    # At the budget and below it the doc is diffed (not skipped).
    assert is_oversized("x" * 10, max_doc_chars=10) is False
    assert is_oversized("x" * 3, max_doc_chars=10) is False
    assert is_oversized("", max_doc_chars=10) is False
