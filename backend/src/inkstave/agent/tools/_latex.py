"""LaTeX heading scan heuristic (spec 42; replaced by a real parser in spec 48)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sectioning commands, highest level first. Index = level rank (lower = higher level).
_LEVELS = ["part", "chapter", "section", "subsection", "subsubsection"]
_LEVEL_RANK = {name: i for i, name in enumerate(_LEVELS)}

_HEADING_RE = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\])?\s*\{(?P<title>[^}]*)\}"
)


@dataclass
class Heading:
    level: str
    title: str
    line: int  # 0-based line index of the heading


def scan_headings(content: str) -> list[Heading]:
    headings: list[Heading] = []
    for i, line in enumerate(content.splitlines()):
        match = _HEADING_RE.search(line)
        if match:
            headings.append(
                Heading(level=match.group(1), title=match.group("title").strip(), line=i)
            )
    return headings


def section_range(headings: list[Heading], index: int, total_lines: int) -> tuple[int, int]:
    """[start_line, end_line) for headings[index]: until the next same-or-higher heading."""
    head = headings[index]
    rank = _LEVEL_RANK[head.level]
    for other in headings[index + 1 :]:
        if _LEVEL_RANK[other.level] <= rank:
            return head.line, other.line
    return head.line, total_lines


def _normalize(text: str) -> str:
    text = text.strip().lower()
    if text.startswith("the "):
        text = text[4:]
    return text


def match_score(query: str, title: str) -> float:
    """1.0 exact, 0.7 substring, else token-overlap ratio (0..0.6), 0 if none."""
    q, t = _normalize(query), _normalize(title)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t or t in q:
        return 0.7
    q_tokens, t_tokens = set(q.split()), set(t.split())
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens) / len(q_tokens)
    return round(overlap * 0.6, 3) if overlap else 0.0
