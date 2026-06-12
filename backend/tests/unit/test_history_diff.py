"""Unit tests for the history text diff (spec 37, criterion 3)."""

from __future__ import annotations

import pytest

from inkstave.collab.ydocument import YDocument
from inkstave.history.diff import apply_hunks, diff_text
from inkstave.history.reconstruct import is_binary, text_from_state

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
