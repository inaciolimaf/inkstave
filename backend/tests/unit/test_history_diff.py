"""Unit tests for the history text diff (spec 37, criterion 3)."""

from __future__ import annotations

import pytest

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.history.versions.diff import apply_hunks, diff_text
from inkstave.modules.history.versions.reconstruct import is_binary, text_from_state

_CASES = [
    ("", "hello\nworld\n"),  # pure insert
    ("a\nb\nc\n", ""),  # pure delete
    ("a\nb\nc\n", "a\nB\nc\n"),  # replace one line
    ("a\nb\nc\nd\ne\n", "a\nb\nX\nd\nY\n"),  # multiple changed regions
    ("\\section{Intro}\nold line\n", "\\section{Intro}\nnew line\nextra\n"),
    ("same\nsame\nsame\n", "same\nsame\nsame\n"),  # identical -> no hunks
    # spec-40 edge cases:
    ("", ""),  # both empty
    ("one line no newline", "one line no newline!"),  # change an unterminated final line
    ("a\nb\nc\n", "x\ny\nz\n"),  # all-removed + all-added
    ("keep\nlast no newline", "keep\nlast changed no newline"),  # final unterminated line
]


@pytest.mark.parametrize(("a", "b"), _CASES)
def test_apply_diff_reproduces_b(a: str, b: str) -> None:
    hunks = diff_text(a, b)
    assert apply_hunks(a, hunks) == b  # criterion 3: A + diff == B


def test_segments_are_context_added_removed_only() -> None:
    hunks = diff_text("a\nb\nc\n", "a\nB\nc\n")
    assert hunks  # there is a change
    types = {seg["type"] for h in hunks for seg in h["segments"]}
    assert types <= {"context", "added", "removed"}
    # the replaced line shows up as removed 'b' + added 'B'
    values = [(seg["type"], seg["value"]) for h in hunks for seg in h["segments"]]
    assert ("removed", "b\n") in values
    assert ("added", "B\n") in values


def test_identical_text_has_no_hunks() -> None:
    assert diff_text("x\ny\n", "x\ny\n") == []


def test_binary_detection() -> None:
    assert is_binary("text\x00with null")
    assert not is_binary("plain latex text")


@pytest.mark.parametrize(
    "value",
    [
        "hello world\n\\section{Intro}\nbody\n",  # ASCII / LaTeX
        "café — naïve ☕ — δοκιμή — 日本語\n",  # multibyte / unicode
    ],
)
def test_text_from_state_matches_reconstruct_encoding(value: str) -> None:
    # §5.4.2 contract: text_from_state on a state produced exactly as
    # reconstruct_state encodes it (YDocument.get_state) returns the document text.
    doc = YDocument()
    doc.replace_text(value)
    state = doc.get_state()
    assert text_from_state(state) == value


def test_a_replacement_gives_one_hunk_with_exact_positions_and_segments() -> None:
    assert diff_text("a\nb\nc\n", "a\nB\nc\n") == [
        {
            "old_start": 1,
            "old_lines": 3,
            "new_start": 1,
            "new_lines": 3,
            "segments": [
                {"type": "context", "value": "a\n"},
                {"type": "removed", "value": "b\n"},
                {"type": "added", "value": "B\n"},
                {"type": "context", "value": "c\n"},
            ],
        }
    ]


def test_hunk_positions_are_one_based_and_count_lines_of_each_side() -> None:
    a = "".join(f"line{i}\n" for i in range(10))
    b = a.replace("line9\n", "changed\n")
    assert diff_text(a, b) == [
        {
            "old_start": 7,
            "old_lines": 4,
            "new_start": 7,
            "new_lines": 4,
            "segments": [
                {"type": "context", "value": "line6\n"},
                {"type": "context", "value": "line7\n"},
                {"type": "context", "value": "line8\n"},
                {"type": "removed", "value": "line9\n"},
                {"type": "added", "value": "changed\n"},
            ],
        }
    ]


def test_an_insertion_moves_only_the_new_side_position() -> None:
    hunks = diff_text("a\nb\nc\n", "a\nb\nX\nc\n")
    assert [(h["old_start"], h["old_lines"], h["new_start"], h["new_lines"]) for h in hunks] == [(1, 3, 1, 4)]


def test_three_lines_of_context_is_the_default() -> None:
    # 7 unchanged lines between two changes: more than 2 * 3, so the default splits them into two hunks.
    a = "x1\n" + "e\n" * 7 + "x2\n"
    b = "y1\n" + "e\n" * 7 + "y2\n"
    hunks = diff_text(a, b)
    assert len(hunks) == 2
    assert [seg["type"] for seg in hunks[0]["segments"]].count("context") == 3
    assert [seg["type"] for seg in hunks[1]["segments"]].count("context") == 3


def test_unchanged_lines_further_than_the_context_are_left_out_of_a_hunk() -> None:
    hunks = diff_text("a\nb\nc\nd\ne\nf\ng\nh\n", "a\nb\nc\nd\ne\nf\ng\nH\n")
    assert len(hunks) == 1
    assert hunks[0]["old_start"] == 5
    assert len(hunks[0]["segments"]) == 5  # 3 context, one removed, one added


def test_a_long_file_is_diffed_without_treating_repeated_lines_as_junk() -> None:
    # SequenceMatcher drops lines that repeat more than 1% of a 200-line-plus file (autojunk).
    # The default must keep them, so a single changed line is one small hunk.
    lines = [f"{i % 5}\n" for i in range(300)]  # every distinct line repeats 60 times: all are popular
    a = "".join(lines)
    b = "".join([*lines[:150], "Z\n", *lines[151:]])
    hunks = diff_text(a, b)
    assert len(hunks) == 1
    assert [seg["type"] for seg in hunks[0]["segments"]] == [
        "context",
        "context",
        "context",
        "removed",
        "added",
        "context",
        "context",
        "context",
    ]


def test_hunks_far_apart_each_apply_at_their_own_position() -> None:
    a = "".join(f"{i}\n" for i in range(12))
    b = a.replace("1\n", "1\nnew\nnew2\n", 1).replace("10\n", "", 1)
    hunks = diff_text(a, b)
    assert len(hunks) == 2  # 8 unchanged lines between the two changes
    assert apply_hunks(a, hunks) == b
    # A hunk that adds lines shifts the lines after it: applying the hunks in any order must still work.
    assert apply_hunks(a, list(reversed(hunks))) == b


def test_hunks_that_change_the_line_count_apply_bottom_up() -> None:
    a = "".join(f"{i}\n" for i in range(20))
    b = a.replace("2\n", "2\nA\nB\nC\n", 1).replace("15\n", "", 1)
    assert apply_hunks(a, diff_text(a, b)) == b
