"""Pure diff computation from staged edits (spec 43). No DB, no LLM, no mutation."""

from __future__ import annotations

import difflib
import hashlib
from typing import TYPE_CHECKING, Any

from inkstave.agent.edits import EditMode

if TYPE_CHECKING:
    from inkstave.agent.edits import StagedEdit


class DiffConflictError(Exception):
    """Overlapping range edits on one document — the proposal cannot be applied."""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_staged_edits(current_text: str, edits: list[StagedEdit]) -> str:
    """Build the proposed content for ONE doc from its staged edits.

    ``full`` wins over any ``range`` edits (ranges ignored). Multiple ``range`` edits
    must be non-overlapping; they are applied bottom-up so earlier indices stay valid.
    Overlapping ranges raise ``DiffConflictError``.
    """
    had_trailing = current_text.endswith("\n")
    fulls = [e for e in edits if e.mode == EditMode.full]
    ranges = [e for e in edits if e.mode == EditMode.range]

    if fulls:
        lines = fulls[-1].new_text.splitlines()
    else:
        lines = current_text.splitlines()
        ordered = sorted(ranges, key=lambda e: e.start_line or 0)
        for a, b in zip(ordered, ordered[1:], strict=False):
            if (a.end_line or 0) > (b.start_line or 0):
                raise DiffConflictError(
                    f"overlapping range edits: [{a.start_line},{a.end_line}) and "
                    f"[{b.start_line},{b.end_line})"
                )
        for edit in sorted(ranges, key=lambda e: e.start_line or 0, reverse=True):
            lines[edit.start_line : edit.end_line] = edit.new_text.splitlines()

    proposed = "\n".join(lines)
    if had_trailing and proposed:
        proposed += "\n"
    return proposed


def _format_range(start: int, stop: int) -> tuple[int, int]:
    """difflib unified-diff range → (1-based beginning shown in @@, length)."""
    length = stop - start
    if length == 1:
        return start + 1, 1
    beginning = start + 1
    if length == 0:
        beginning -= 1  # empty ranges begin at the line just before the range
    return beginning, length


def _fmt(begin: int, length: int) -> str:
    return str(begin) if length == 1 else f"{begin},{length}"


def _hunk_lines(
    group: list[tuple[str, int, int, int, int]], a: list[str], b: list[str]
) -> tuple[list[dict[str, str]], int, int]:
    """The ``+``/``-``/context lines of one opcode group, with its add/delete counts."""
    lines: list[dict[str, str]] = []
    adds = dels = 0
    for tag, i1, i2, j1, j2 in group:
        if tag == "equal":
            lines.extend({"op": " ", "text": line} for line in a[i1:i2])
            continue
        if tag in ("replace", "delete"):
            lines.extend({"op": "-", "text": line} for line in a[i1:i2])
            dels += i2 - i1
        if tag in ("replace", "insert"):
            lines.extend({"op": "+", "text": line} for line in b[j1:j2])
            adds += j2 - j1
    return lines, adds, dels


def _hunk(
    index: int, group: list[tuple[str, int, int, int, int]], a: list[str], b: list[str]
) -> dict[str, Any]:
    """One hunk of the unified diff, headers and counts included."""
    old_begin, old_len = _format_range(group[0][1], group[-1][2])
    new_begin, new_len = _format_range(group[0][3], group[-1][4])
    lines, adds, dels = _hunk_lines(group, a, b)
    return {
        "hunk_id": f"h{index}",
        "header": f"@@ -{_fmt(old_begin, old_len)} +{_fmt(new_begin, new_len)} @@",
        "old_start": old_begin,
        "old_lines": old_len,
        "new_start": new_begin,
        "new_lines": new_len,
        "lines": lines,
        "additions": adds,
        "deletions": dels,
    }


def _render(path: str, hunks: list[dict[str, Any]]) -> str:
    """The unified-diff text for a non-empty hunk list."""
    body: list[str] = []
    for hunk in hunks:
        body.append(str(hunk["header"]))
        body.extend(f"{line['op']}{line['text']}" for line in hunk["lines"])
    return "\n".join([f"--- a/{path}", f"+++ b/{path}", *body])


def _stats(hunks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "additions": sum(int(h["additions"]) for h in hunks),
        "deletions": sum(int(h["deletions"]) for h in hunks),
        "hunk_count": len(hunks),
    }


def compute_diff(
    current: str, proposed: str, *, path: str, context: int = 3
) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Return (unified diff_text, ordered hunks, stats). Empty when current==proposed."""
    a = current.splitlines()
    b = proposed.splitlines()
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    hunks = [
        _hunk(index, group, a, b)
        for index, group in enumerate(matcher.get_grouped_opcodes(context), start=1)
    ]
    if not hunks:
        return "", [], {"additions": 0, "deletions": 0, "hunk_count": 0}
    return _render(path, hunks), hunks, _stats(hunks)
