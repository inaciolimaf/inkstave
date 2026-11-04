"""Three-way merge of a pushed text file into the live document (spec 121).

``old`` is the text the writer's clone was based on, ``new`` is the pushed text and ``live`` is what the
document says now. The push is the diff ``old -> new``. Each of its hunks is mapped into ``live`` through
the alignment of ``old`` and ``live``, so a hunk lands where its lines are now, even when collaborators
inserted lines above it. A hunk whose lines collaborators also changed is still applied, replacing that
region, and is reported as a conflict. Everything is computed on plain strings; the caller applies the
edits through the CRDT.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True, slots=True)
class TextEdit:
    """Replace ``live[start:end]`` with ``text``; offsets are character positions in the live text."""

    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class Conflict:
    """A region the push replaced although collaborators had changed it.

    Lines are 1-based and count in the pushed text.
    """

    first_line: int
    last_line: int


@dataclass(slots=True)
class _Span:
    live_start: int  # line index in the live text
    live_end: int
    new_start: int  # line index in the pushed text
    new_end: int
    conflict: bool


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _opcodes(a: list[str], b: list[str]) -> Sequence[tuple[str, int, int, int, int]]:
    return SequenceMatcher(None, a, b, autojunk=False).get_opcodes()


class _Alignment:
    """How old line indexes map onto the live text, and which old lines collaborators changed."""

    def __init__(self, old: list[str], live: list[str]) -> None:
        self.position = [0] * (len(old) + 1)
        self.touched = [False] * (len(old) + 1)
        for tag, a1, a2, b1, b2 in _opcodes(old, live):
            if tag == "equal":
                for k in range(a1, a2 + 1):
                    self.position[k] = b1 + (k - a1)
                continue
            for k in range(a1, a2):
                self.touched[k] = True
            self.position[a1] = b1
            self.position[a2] = b2
            for k in range(a1 + 1, a2):
                self.position[k] = b1

    def conflicts(self, i1: int, i2: int) -> bool:
        if i1 < i2:
            return any(self.touched[k] for k in range(i1, i2))
        # A pure insertion inside a region collaborators changed.
        return 0 < i1 < len(self.touched) - 1 and self.touched[i1 - 1] and self.touched[i1]


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    """Join spans whose live ranges touch or overlap.

    Their pushed text is contiguous, so the union is exact.
    """
    merged: list[_Span] = []
    for span in spans:
        if merged and span.live_start <= merged[-1].live_end:
            previous = merged[-1]
            previous.live_end = max(previous.live_end, span.live_end)
            previous.new_end = span.new_end
            previous.conflict = previous.conflict or span.conflict
        else:
            merged.append(span)
    return merged


def _trim(start: int, old_text: str, new_text: str) -> TextEdit:
    """Shrink an edit to the part that really differs, so the CRDT receives the smallest change."""
    prefix = 0
    limit = min(len(old_text), len(new_text))
    while prefix < limit and old_text[prefix] == new_text[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and old_text[-1 - suffix] == new_text[-1 - suffix]:
        suffix += 1
    end_old = len(old_text) - suffix
    return TextEdit(start + prefix, start + end_old, new_text[prefix : len(new_text) - suffix])


def _spans_for(old: list[str], live: list[str], new: list[str]) -> list[_Span]:
    alignment = _Alignment(old, live)
    spans: list[_Span] = []
    for tag, i1, i2, j1, j2 in _opcodes(old, new):
        if tag == "equal":
            continue
        spans.append(
            _Span(
                live_start=alignment.position[i1],
                live_end=alignment.position[i2],
                new_start=j1,
                new_end=j2,
                conflict=alignment.conflicts(i1, i2),
            )
        )
    return spans


def plan_text_edits(live: str, old: str, new: str) -> tuple[list[TextEdit], list[Conflict]]:
    """Edits that turn ``live`` into ``live`` with the push ``old -> new`` applied, and the conflicts.

    The edits are ordered from the end of the text to the start, so applying them in order never moves
    an offset that is still to be used.
    """
    old_lines, live_lines, new_lines = _lines(old), _lines(live), _lines(new)
    if old_lines == new_lines:
        return [], []
    offsets = [0]
    for line in live_lines:
        offsets.append(offsets[-1] + len(line))

    edits: list[TextEdit] = []
    conflicts: list[Conflict] = []
    for span in _merge_spans(_spans_for(old_lines, live_lines, new_lines)):
        old_region = "".join(live_lines[span.live_start : span.live_end])
        new_region = "".join(new_lines[span.new_start : span.new_end])
        edit = _trim(offsets[span.live_start], old_region, new_region)
        if edit.start != edit.end or edit.text:
            edits.append(edit)
        if span.conflict:
            conflicts.append(Conflict(span.new_start + 1, max(span.new_end, span.new_start + 1)))
    edits.sort(key=lambda edit: edit.start, reverse=True)
    return edits, conflicts
