"""Apply a unified diff, as the agent proposes it, to a text (test helper)."""

from __future__ import annotations

import re

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$")


def apply_unified(current: str, diff_text: str) -> str:
    """Apply ``diff_text`` (as ``compute_diff`` renders it) to ``current``.

    Every context and removed line must match the current file, or the assertion fails: the
    diff is only correct if it applies to the text the user has now.
    """
    source = current.splitlines()
    out: list[str] = []
    pos = 0
    for line in diff_text.splitlines()[2:]:  # skip the ---/+++ header
        header = _HUNK_HEADER.match(line)
        if header:
            old_start, old_len = int(header.group(1)), int(header.group(2) or 1)
            start = old_start if old_len == 0 else old_start - 1
            out.extend(source[pos:start])
            pos = start
            continue
        op, text = line[:1], line[1:]
        if op == "+":
            out.append(text)
            continue
        assert source[pos] == text, f"diff does not match the current file at line {pos + 1}"
        pos += 1
        if op == " ":
            out.append(text)
    out.extend(source[pos:])
    return "\n".join(out) + "\n"
