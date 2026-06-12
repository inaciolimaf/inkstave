"""Prompt-injection mitigations (spec 49): untrusted framing + heuristic flagging."""

from __future__ import annotations

import re

# Deterministic override-pattern heuristics. Best-effort — must not block edits.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(above|previous|system|prior)", re.I),
    re.compile(r"^\s*system\s*:", re.I | re.M),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(
        r"(reveal|print|show|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions)", re.I
    ),
    re.compile(r"new\s+(system\s+)?instructions\s*:", re.I),
    re.compile(r"override\s+(your|the)\s+(rules|instructions|guardrails)", re.I),
]


def flag_injection(text: str) -> bool:
    """True if the text contains a known prompt-override pattern (deterministic)."""
    return any(p.search(text) for p in _PATTERNS)


def wrap_untrusted(label: str, text: str) -> str:
    """Wrap untrusted content in a clearly-delimited, labelled block."""
    tag = f"untrusted_{label}"
    return f"<{tag}>\n{text}\n</{tag}>"
