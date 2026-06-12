"""Unit tests for agent tools: heuristic, schemas, registry (spec 42)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from inkstave.agent.tools import default_registry
from inkstave.agent.tools._latex import match_score, scan_headings, section_range
from inkstave.agent.tools.base import ToolContext
from inkstave.agent.tools.list_tree import ListTreeArgs
from inkstave.agent.tools.locate_section import LocateSectionArgs
from inkstave.agent.tools.propose_edit import ProposeEditArgs
from inkstave.agent.tools.read_file import ReadFileArgs
from inkstave.agent.tools.search_project import (
    _PAYLOAD_SOFT_CAP,
    _SNIPPET_MAX,
    SearchProjectArgs,
)

_DOC = "\n".join(
    [
        r"\section{Introduction}",  # 0
        "intro body",  # 1
        r"\subsection{Background}",  # 2
        "bg body",  # 3
        r"\section*{Methods}",  # 4 (starred)
        "methods body",  # 5
    ]
)


def test_scan_headings_finds_sections_and_starred() -> None:
    heads = scan_headings(_DOC)
    assert [(h.level, h.title, h.line) for h in heads] == [
        ("section", "Introduction", 0),
        ("subsection", "Background", 2),
        ("section", "Methods", 4),
    ]


def test_section_range_to_next_same_or_higher() -> None:
    heads = scan_headings(_DOC)
    total = len(_DOC.splitlines())
    # Introduction (section) runs to the next section (Methods), spanning the subsection.
    assert section_range(heads, 0, total) == (0, 4)
    # Background (subsection) runs to the next same-or-higher heading (Methods).
    assert section_range(heads, 1, total) == (2, 4)
    # Methods runs to EOF.
    assert section_range(heads, 2, total) == (4, total)


def test_match_score_exact_substring_article_token() -> None:
    assert match_score("Introduction", "Introduction") == 1.0
    assert match_score("the introduction", "Introduction") == 1.0  # leading article dropped
    assert match_score("intro", "Introduction") == 0.7  # substring
    assert match_score("related work", "Related Work and Background") == 0.7
    assert 0 < match_score("introduction methods", "methods chapter") < 0.7  # token overlap only
    assert match_score("nonsense", "Introduction") == 0.0


def test_read_file_args_require_exactly_one_selector() -> None:
    with pytest.raises(ValidationError):
        ReadFileArgs()  # neither
    with pytest.raises(ValidationError):
        ReadFileArgs(doc_id="d", path="p")  # both
    ReadFileArgs(doc_id="d")  # ok


def test_propose_edit_args_range_requires_lines() -> None:
    with pytest.raises(ValidationError):
        ProposeEditArgs(doc_id="d", mode="range", new_text="x")
    ProposeEditArgs(doc_id="d", mode="range", new_text="x", start_line=0, end_line=2)
    ProposeEditArgs(doc_id="d", mode="full", new_text="x")  # full needs no lines


def test_search_project_args_reject_empty_query() -> None:
    with pytest.raises(ValidationError):
        SearchProjectArgs(query="")  # min_length=1
    assert SearchProjectArgs(query="theorem").query == "theorem"  # happy


def test_locate_section_args_reject_empty_name() -> None:
    with pytest.raises(ValidationError):
        LocateSectionArgs(name="")  # min_length=1
    assert LocateSectionArgs(name="Introduction").name == "Introduction"  # happy


def test_list_tree_args_construct_for_valid_input() -> None:
    # Defaults (happy).
    default = ListTreeArgs()
    assert default.path is None
    assert default.depth == 3
    # Explicit valid input (happy).
    explicit = ListTreeArgs(path="src/main.tex", depth=5)
    assert explicit.path == "src/main.tex"
    assert explicit.depth == 5


async def test_search_project_caps_snippet_and_truncates_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_project caps snippets at 240 chars and soft-caps the payload (AC 2)."""
    from dataclasses import dataclass

    from inkstave.agent.tools import search_project as sp
    from inkstave.db.models.tree_entity import TreeEntityType

    @dataclass
    class _Entity:
        id: UUID
        type: TreeEntityType

    # Synthetic in-memory corpus: many long lines all containing the needle, so
    # the bounded-payload loop must trip the 8 KB soft cap (each match ~ snippet
    # + 64 bytes of envelope; with 240-char snippets ~27 matches exceed 8 KB).
    doc_id = uuid4()
    long_line = "needle " + ("x" * 400)  # > 240 chars after the needle
    content = "\n".join(long_line for _ in range(60))

    entities = [_Entity(id=doc_id, type=TreeEntityType.doc)]
    paths = {doc_id: "main.tex"}

    async def fake_load_tree(_ctx: object) -> tuple[list[_Entity], dict[UUID, str]]:
        return entities, paths

    async def fake_read_content(_db: object, _entity_id: UUID) -> str:
        return content

    async def fake_authorize(_ctx: object, **_kw: object) -> None:
        return None

    monkeypatch.setattr(sp, "load_tree", fake_load_tree)
    monkeypatch.setattr(sp, "read_content_for_collab", fake_read_content)
    monkeypatch.setattr(sp, "authorize", fake_authorize)

    class _Settings:
        agent_tool_search_max_results = 50

    ctx = ToolContext(
        db=None,  # type: ignore[arg-type]
        project_id=str(uuid4()),
        user_id=str(uuid4()),
        settings=_Settings(),  # type: ignore[arg-type]
    )

    result = await sp.SearchProjectTool().run(SearchProjectArgs(query="needle"), ctx)

    assert result.ok
    matches = result.data["matches"]
    assert matches, "expected at least one match"
    # Every snippet is capped at the 240-char maximum.
    assert all(len(m["snippet"]) <= _SNIPPET_MAX for m in matches)
    # The synthetic corpus overflows the 8 KB soft cap, so the result is truncated.
    assert result.data["truncated"] is True
    payload_size = sum(len(m["snippet"]) + 64 for m in matches)
    assert payload_size <= _PAYLOAD_SOFT_CAP


def test_registry_specs_are_valid_json_schema() -> None:
    registry = default_registry()
    specs = registry.specs()
    assert {s.name for s in specs} == {
        "search_project",
        "read_file",
        "list_tree",
        "locate_section",
        "propose_edit",
    }
    for spec in specs:
        assert spec.description
        assert spec.parameters.get("type") == "object"
        assert "properties" in spec.parameters
