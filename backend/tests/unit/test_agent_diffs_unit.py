"""Unit tests for diff computation (spec 43): pure, no DB."""

from __future__ import annotations

from difflib import unified_diff
from types import SimpleNamespace
from typing import cast

import pytest

from inkstave.modules.agent.diffs import is_oversized, is_stale
from inkstave.modules.agent.diffs.compute import (
    DiffConflictError,
    apply_staged_edits,
    compute_diff,
    content_hash,
)
from inkstave.modules.agent.diffs.models import ProposedDiff
from inkstave.modules.agent.graph.edits import StagedEdit


def _edit(old_text: str, new_text: str) -> StagedEdit:
    return StagedEdit(
        edit_id="e", doc_id="d", path="f.tex", base_version="1", old_text=old_text, new_text=new_text
    )


def test_single_replacement_keeps_the_rest_of_the_text() -> None:
    assert apply_staged_edits("a\nb\nc\nd\n", [_edit("b\n", "B\n")]) == "a\nB\nc\nd\n"


def test_replacement_may_span_and_change_line_breaks() -> None:
    assert apply_staged_edits("a\nb\nc\n", [_edit("b\nc", "x")]) == "a\nx\n"


def test_empty_old_text_fills_an_empty_file() -> None:
    assert apply_staged_edits("", [_edit("", "new\n")]) == "new\n"


def test_empty_old_text_is_refused_for_a_non_empty_file() -> None:
    with pytest.raises(DiffConflictError):
        apply_staged_edits("a\n", [_edit("", "new\n")])


def test_old_text_absent_raises_conflict() -> None:
    with pytest.raises(DiffConflictError):
        apply_staged_edits("a\nb\n", [_edit("zzz", "y")])


def test_old_text_repeated_raises_conflict() -> None:
    with pytest.raises(DiffConflictError):  # never guesses which occurrence was meant
        apply_staged_edits("x\nx\n", [_edit("x", "y")])


def test_successive_edits_apply_to_the_text_the_previous_one_left() -> None:
    # The second edit's old_text exists only after the first has run.
    edits = [_edit("alpha", "beta"), _edit("beta gamma", "delta")]
    assert apply_staged_edits("alpha gamma\n", edits) == "delta\n"


def test_second_edit_that_no_longer_fits_raises_conflict() -> None:
    edits = [_edit("alpha", "beta"), _edit("alpha", "gamma")]
    with pytest.raises(DiffConflictError):
        apply_staged_edits("alpha\n", edits)


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


def test_is_stale_on_version_or_hash_change() -> None:
    diff = cast(ProposedDiff, SimpleNamespace(base_version="3", base_hash=content_hash("abc")))
    assert is_stale(diff, "abc", 3) is False  # AC6: unchanged
    assert is_stale(diff, "abc", 4) is True  # version changed
    assert is_stale(diff, "abcX", 3) is True  # hash changed


def test_is_oversized_skips_past_threshold() -> None:
    # AC9: a document strictly larger than the budget is skipped (the > branch).
    assert is_oversized("x" * 11, max_doc_chars=10) is True


def test_is_oversized_keeps_at_or_under_threshold() -> None:
    # At the budget and below it the doc is diffed (not skipped).
    assert is_oversized("x" * 10, max_doc_chars=10) is False
    assert is_oversized("x" * 3, max_doc_chars=10) is False
    assert is_oversized("", max_doc_chars=10) is False


def test_default_context_is_three_lines() -> None:
    current = "".join(f"{i}\n" for i in range(10))
    proposed = current.replace("5\n", "X\n")
    text, _hunks, _stats = compute_diff(current, proposed, path="f.tex")
    expected = list(
        unified_diff(current.splitlines(), proposed.splitlines(), "a/f.tex", "b/f.tex", lineterm="")
    )
    assert text == "\n".join(expected)


def test_a_small_edit_in_a_long_file_of_repeated_lines_stays_small() -> None:
    # Lines that repeat often are not treated as junk (autojunk off): one changed line is one hunk line.
    current = "\n".join(["}"] * 120 + ["target"] + ["}"] * 120) + "\n"
    proposed = current.replace("target", "new")
    _text, hunks, stats = compute_diff(current, proposed, path="f.tex")
    assert stats == {"additions": 1, "deletions": 1, "hunk_count": 1}
    assert len(hunks) == 1


_DIFF_CASES = [
    ("", "a\nb\n"),  # everything added to an empty file
    ("a\nb\n", ""),  # everything removed
    ("a\nb\nc\n", "a\nX\nc\n"),  # one line replaced
    ("a\n", "x\na\n"),  # insert before the first line
    ("a\n", "a\nx\n"),  # insert after the last line
    ("a\nb\nc\nd\ne\nf\ng\nh\n", "a\nb\nc\nd\ne\nf\nG\nh\n"),  # change far from the top
    ("1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n", "1\n2\nX\n4\n5\n6\n7\n8\n9\nY\n"),  # two hunks
    ("a\nb\nc\nd\n", "a\nc\nd\nb\n"),  # a line moved
    ("a\nb\nc\n", "a\nb\nc\n"),  # no change
]


@pytest.mark.parametrize(("current", "proposed"), _DIFF_CASES)
@pytest.mark.parametrize("context", [0, 1, 3])
def test_compute_diff_matches_difflib_text_and_stats(current: str, proposed: str, context: int) -> None:
    # difflib is the oracle: the headers (range rules included) and every body line must agree.
    diff_text, hunks, stats = compute_diff(current, proposed, path="f.tex", context=context)
    expected = list(
        unified_diff(
            current.splitlines(), proposed.splitlines(), "a/f.tex", "b/f.tex", n=context, lineterm=""
        )
    )
    assert diff_text == "\n".join(expected)
    body = expected[2:]
    assert stats == {
        "additions": sum(1 for line in body if line.startswith("+")),
        "deletions": sum(1 for line in body if line.startswith("-")),
        "hunk_count": len(hunks),
    }


def test_each_hunk_carries_its_own_id_counts_and_ranges() -> None:
    current = "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"
    proposed = "1\n2\nX\n4\n5\n6\n7\n8\n9\nY\n"
    _text, hunks, stats = compute_diff(current, proposed, path="f.tex", context=1)

    assert [h["hunk_id"] for h in hunks] == ["h1", "h2"]
    assert [h["header"] for h in hunks] == ["@@ -2,3 +2,3 @@", "@@ -9,2 +9,2 @@"]
    assert [(h["old_start"], h["old_lines"], h["new_start"], h["new_lines"]) for h in hunks] == [
        (2, 3, 2, 3),
        (9, 2, 9, 2),
    ]
    assert [(h["additions"], h["deletions"]) for h in hunks] == [(1, 1), (1, 1)]
    assert stats == {"additions": 2, "deletions": 2, "hunk_count": 2}


def test_a_hunk_mixing_replace_and_insert_counts_both_sides() -> None:
    # One hunk holds a replacement and a pure insertion: the counts add up across opcodes.
    _text, hunks, stats = compute_diff("a\nb\nc\n", "a\nB1\nB2\nc\nd\n", path="f.tex", context=3)
    assert len(hunks) == 1
    assert (hunks[0]["additions"], hunks[0]["deletions"]) == (3, 1)
    assert stats == {"additions": 3, "deletions": 1, "hunk_count": 1}


def test_a_no_op_diff_reports_zero_stats() -> None:
    assert compute_diff("x\n", "x\n", path="f.tex") == (
        "",
        [],
        {"additions": 0, "deletions": 0, "hunk_count": 0},
    )
