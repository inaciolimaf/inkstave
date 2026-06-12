"""Structure-aware section resolution (spec 48). Deterministic, no LLM."""

from __future__ import annotations

import re

from inkstave.agent.context.models import ProjectMap, SectionMatch, StructureKind, StructureNode

# Common section synonyms → the canonical word that appears in titles.
_SYNONYMS: dict[str, str] = {
    "intro": "introduction",
    "introduction": "introduction",
    "methods": "method",
    "methodology": "method",
    "method": "method",
    "related work": "related work",
    "background": "background",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "abstract": "abstract",
    "results": "result",
    "discussion": "discussion",
    "references": "references",
    "bibliography": "references",
    "appendix": "appendix",
}

_ORDINALS: dict[str, int] = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
}

_SECTION_WORDS = "part|chapter|section|subsection|subsubsection|paragraph|subparagraph"


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip().lower())
    return text[4:] if text.startswith("the ") else text


def _concepts(query: str) -> set[str]:
    """Canonical concepts a query refers to (whole phrase + each token)."""
    found: set[str] = set()
    if query in _SYNONYMS:
        found.add(_SYNONYMS[query])
    for token in query.split():
        if token in _SYNONYMS:
            found.add(_SYNONYMS[token])
    return found


def _flatten(nodes: list[StructureNode]) -> list[StructureNode]:
    out: list[StructureNode] = []
    for node in nodes:
        if node.kind == StructureKind.SECTIONING:
            out.append(node)
        out.extend(_flatten(node.children))
    return out


def _ordinal_match(query: str, sections: list[StructureNode]) -> SectionMatch | None:
    """Resolve 'section 2' / 'the first subsection' to the Nth node of that command."""
    m = re.search(rf"({_SECTION_WORDS})\s+(\d+)", query)
    if m:
        word, num = m.group(1), int(m.group(2))
    else:
        m = re.search(rf"(\w+)\s+({_SECTION_WORDS})", query)
        if not m or m.group(1) not in _ORDINALS:
            return None
        word, num = m.group(2), _ORDINALS[m.group(1)]
    matching = [n for n in sections if n.command == word]
    if 1 <= num <= len(matching):
        return SectionMatch(node=matching[num - 1], score=0.92, reason=f"{word} #{num}")
    return None


def locate_section(project_map: ProjectMap, query: str) -> list[SectionMatch]:
    sections = _flatten(project_map.outline)
    if not sections:
        return []
    q = _normalize(query)

    ordinal = _ordinal_match(q, sections)
    if ordinal is not None:
        return [ordinal]

    matches: list[SectionMatch] = []
    concepts = _concepts(q)
    q_tokens = set(q.split())
    for node in sections:
        title = _normalize(node.title or "")
        label = (node.label or "").lower()
        score = 0.0
        reason = ""
        if title and q == title:
            score, reason = 1.0, "exact title"
        elif label and q == label:
            score, reason = 0.95, "label"
        elif concepts and title and any(c in title for c in concepts):
            score, reason = 0.9, "synonym"
        elif title and (q in title or title in q):
            score, reason = 0.7, "substring"
        elif title:
            overlap = len(q_tokens & set(title.split())) / max(1, len(q_tokens))
            if overlap:
                score, reason = round(overlap * 0.6, 3), "token overlap"
        if score > 0:
            matches.append(SectionMatch(node=node, score=score, reason=reason))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
