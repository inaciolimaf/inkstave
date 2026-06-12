"""Line-level unified text diff (spec 37, §5.2.3).

A `difflib`-based line diff grouped into hunks of `context | added | removed`
segments. Segment granularity is **line-level** (documented choice; word-level
refinement is left to spec 38's renderer). `apply_hunks` reconstructs the new text
from the old + hunks, which the tests use to prove a diff round-trips.
"""

from __future__ import annotations

import difflib
from typing import Literal, TypedDict

SegmentType = Literal["context", "added", "removed"]


class Segment(TypedDict):
    type: SegmentType
    value: str


class Hunk(TypedDict):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    segments: list[Segment]


def diff_text(a: str, b: str, *, context: int = 3) -> list[Hunk]:
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    hunks: list[Hunk] = []
    for group in matcher.get_grouped_opcodes(context):
        segments: list[Segment] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                segments.extend({"type": "context", "value": line} for line in a_lines[i1:i2])
            else:
                segments.extend({"type": "removed", "value": line} for line in a_lines[i1:i2])
                segments.extend({"type": "added", "value": line} for line in b_lines[j1:j2])
        old_start, old_end = group[0][1], group[-1][2]
        new_start, new_end = group[0][3], group[-1][4]
        hunks.append(
            {
                "old_start": old_start + 1,
                "old_lines": old_end - old_start,
                "new_start": new_start + 1,
                "new_lines": new_end - new_start,
                "segments": segments,
            }
        )
    return hunks


def apply_hunks(a: str, hunks: list[Hunk]) -> str:
    """Reconstruct the new text by applying hunks to ``a`` (right-to-left)."""
    lines = a.splitlines(keepends=True)
    for hunk in sorted(hunks, key=lambda h: h["old_start"], reverse=True):
        new_content = [s["value"] for s in hunk["segments"] if s["type"] in ("context", "added")]
        start = hunk["old_start"] - 1
        lines[start : start + hunk["old_lines"]] = new_content
    return "".join(lines)
