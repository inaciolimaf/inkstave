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
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
}

_SECTION_WORDS = "part|chapter|section|subsection|subsubsection|paragraph|subparagraph"

# Section-match score tiers, strongest → weakest. Higher wins on ties (exact title
# is the self-evident 1.0 sentinel above these).
_SCORE_LABEL_MATCH = 0.95  # exact \label{...} match — near-certain intent
_SCORE_ORDINAL = 0.92  # positional match e.g. "section 2" / "first subsection"
_SCORE_SYNONYM = 0.9  # a known synonym concept appears in the title
_SCORE_SUBSTRING = 0.7  # query is a substring of the title (or vice-versa)
_SCORE_TOKEN_OVERLAP = 0.6  # multiplier on the shared-token fraction (fuzzy fallback)


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
        return SectionMatch(node=matching[num - 1], score=_SCORE_ORDINAL, reason=f"{word} #{num}")
    return None


def _exact_score(
    title: str, label: str, query: str, concepts: set[str]
) -> tuple[float, str] | None:
    """The first exact/synonym rule that fires, or ``None`` to fall through to fuzzy."""
    if title and query == title:
        return 1.0, "exact title"
    if label and query == label:
        return _SCORE_LABEL_MATCH, "label"
    if concepts and title and any(c in title for c in concepts):
        return _SCORE_SYNONYM, "synonym"
    return None


def _fuzzy_score(title: str, query: str, query_tokens: set[str]) -> tuple[float, str]:
    """Substring, then token-overlap scoring; ``(0.0, "")`` when neither hits."""
    if not title:
        return 0.0, ""
    if query in title or title in query:
        return _SCORE_SUBSTRING, "substring"
    overlap = len(query_tokens & set(title.split())) / max(1, len(query_tokens))
    if not overlap:
        return 0.0, ""
    return round(overlap * _SCORE_TOKEN_OVERLAP, 3), "token overlap"


def _score_node(
    node: StructureNode, query: str, concepts: set[str], query_tokens: set[str]
) -> tuple[float, str]:
    """How well one heading answers `query`; ``(0.0, "")`` when it does not."""
    title = _normalize(node.title or "")
    exact = _exact_score(title, (node.label or "").lower(), query, concepts)
    return exact if exact is not None else _fuzzy_score(title, query, query_tokens)


def locate_section(project_map: ProjectMap, query: str) -> list[SectionMatch]:
    sections = _flatten(project_map.outline)
    if not sections:
        return []
    q = _normalize(query)

    ordinal = _ordinal_match(q, sections)
    if ordinal is not None:
        return [ordinal]

    concepts = _concepts(q)
    q_tokens = set(q.split())
    matches = [
        SectionMatch(node=node, score=score, reason=reason)
        for node, (score, reason) in (
            (node, _score_node(node, q, concepts, q_tokens)) for node in sections
        )
        if score > 0
    ]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
