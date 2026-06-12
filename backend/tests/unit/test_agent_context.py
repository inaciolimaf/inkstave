"""Unit tests for the LaTeX parser, project map, locate, and context select (spec 48)."""

from __future__ import annotations

from inkstave.agent.context import (
    build_project_map,
    estimate_tokens,
    locate_section,
    parse_latex_structure,
    select_context,
)
from inkstave.agent.context.models import StructureKind

_DOC = "\n".join(
    [
        r"\documentclass{article}",  # 1
        r"\begin{document}",  # 2
        r"\section{Introduction}",  # 3
        r"\label{sec:intro}",  # 4
        "intro text",  # 5
        r"\subsection{Motivation}",  # 6
        "why",  # 7
        r"\section*{Methods}",  # 8 (starred)
        "% \\section{commented out}",  # 9
        r"\begin{verbatim}",  # 10
        r"\section{not a section}",  # 11
        r"\end{verbatim}",  # 12
        "methods body",  # 13
        r"\end{document}",  # 14
    ]
)


def _sections(nodes):
    out = []
    for n in nodes:
        if n.kind == StructureKind.SECTIONING:
            out.append(n)
        out.extend(_sections(n.children))
    return out


def test_parse_nesting_levels_and_ranges() -> None:  # AC1
    nodes = parse_latex_structure(_DOC, "main.tex")
    secs = _sections(nodes)
    titles = [(s.command, s.title, s.level, s.start_line, s.end_line) for s in secs]
    assert ("section", "Introduction", 1, 3, 7) in titles
    assert ("subsection", "Motivation", 2, 6, 7) in titles
    assert ("section", "Methods", 1, 8, 14) in titles  # starred captured


_ALL_LEVELS = "\n".join(
    [
        r"\part{Part One}",  # 1
        r"\chapter{Chapter One}",  # 2
        r"\section{Alpha}",  # 3
        "alpha body",  # 4
        r"\subsection{Alpha Sub}",  # 5
        "sub body",  # 6
        r"\subsubsection{Deep}",  # 7
        "deep body",  # 8
        r"\paragraph{Para}",  # 9
        "para body",  # 10
        r"\subparagraph{SubPara}",  # 11
        "subpara body",  # 12
        r"\section{Beta}",  # 13
        "beta body",  # 14
    ]
)


def test_parse_all_sectioning_levels_and_nesting() -> None:  # AC1, issue 200
    secs = _sections(parse_latex_structure(_ALL_LEVELS, "main.tex"))
    by_title = {s.title: s for s in secs}
    # (command, level, start_line, end_line) for every level in LaTeX's hierarchy.
    expected = {
        "Part One": ("part", -1, 1, 14),
        "Chapter One": ("chapter", 0, 2, 14),
        "Alpha": ("section", 1, 3, 12),
        "Alpha Sub": ("subsection", 2, 5, 12),
        "Deep": ("subsubsection", 3, 7, 12),
        "Para": ("paragraph", 4, 9, 12),
        "SubPara": ("subparagraph", 5, 11, 12),
        "Beta": ("section", 1, 13, 14),
    }
    for title, (command, level, start_line, end_line) in expected.items():
        node = by_title[title]
        assert (node.command, node.level, node.start_line, node.end_line) == (
            command,
            level,
            start_line,
            end_line,
        )


def test_parse_char_ranges_are_accurate() -> None:  # AC1, issue 202
    secs = _sections(parse_latex_structure(_ALL_LEVELS, "main.tex"))
    by_title = {s.title: s for s in secs}
    alpha = by_title["Alpha"]
    beta = by_title["Beta"]
    # start_char is the byte/char offset of the heading command in the source.
    assert _ALL_LEVELS[alpha.start_char :].startswith(r"\section{Alpha}")
    assert alpha.start_char == 38
    assert beta.start_char == 191
    # end_char of a section extends to just before the next sibling's heading.
    assert alpha.end_char == beta.start_char - 1 == 190


def test_parse_excludes_comments_and_verbatim() -> None:  # AC2
    secs = _sections(parse_latex_structure(_DOC, "main.tex"))
    titles = [s.title for s in secs]
    assert "commented out" not in titles
    assert "not a section" not in titles
    assert titles.count("Methods") == 1


def test_parse_captures_label_and_inputs() -> None:
    nodes = parse_latex_structure(_DOC, "main.tex")
    intro = next(s for s in _sections(nodes) if s.title == "Introduction")
    assert intro.label == "sec:intro"
    # \input, \include and \subfile are all captured as INPUT nodes (issue 201).
    inputs = parse_latex_structure(r"\input{ch1}\include{ch2}\subfile{path/to/part}", "main.tex")
    input_nodes = [n for n in inputs if n.kind == StructureKind.INPUT]
    assert {n.title for n in input_nodes} == {"ch1", "ch2", "path/to/part"}
    subfile = next(n for n in input_nodes if n.command == "subfile")
    assert subfile.kind == StructureKind.INPUT and subfile.title == "path/to/part"


def test_parse_is_robust_to_malformed_input() -> None:  # AC7
    for bad in [r"\section{unclosed", r"\begin{figure}", "\\\\\\ stray", r"\section{}{}{"]:
        parse_latex_structure(bad, "x.tex")  # must not raise


def test_verbatim_percent_does_not_swallow_rest_of_file() -> None:
    # spec 50 fix: a literal '%' before an inline \end{verbatim} must not hide the close.
    text = "\n".join(
        [
            r"\section{One}",
            r"\begin{verbatim}",
            r"code with 50% then \end{verbatim}",
            r"\section{Two}",
            "after",
        ]
    )
    titles = [s.title for s in _sections(parse_latex_structure(text, "x.tex"))]
    assert "One" in titles and "Two" in titles  # Two is not swallowed by verbatim


# --- locate_section --------------------------------------------------------- #


def _map(text: str):
    return build_project_map("p1", ["main.tex"], {"main.tex": text}.get)


def test_locate_synonyms_ordinals_and_no_match() -> None:  # AC4
    text = "\n".join(
        [r"\section{Introduction}", "a", r"\section{Methodology}", "b", r"\section{Abstract}", "c"]
    )
    pm = _map(text)
    assert locate_section(pm, "the introduction")[0].node.title == "Introduction"
    assert locate_section(pm, "the methods section")[0].node.title == "Methodology"  # synonym
    assert locate_section(pm, "section 2")[0].node.title == "Methodology"  # ordinal
    assert locate_section(pm, "the abstract")[0].node.title == "Abstract"
    assert locate_section(pm, "quantum flux capacitor") == []


def test_locate_by_label() -> None:
    pm = _map("\n".join([r"\section{Introduction}", r"\label{intro}", "x"]))
    assert locate_section(pm, "intro")[0].reason in {"label", "synonym", "exact title"}


# --- select_context --------------------------------------------------------- #


def test_select_respects_budget_and_truncates() -> None:  # AC5
    body = "\n".join(f"line {i}" for i in range(200))
    text = f"\\section{{Introduction}}\n{body}\n\\section{{Methods}}\nm\n"
    pm = build_project_map("p1", ["main.tex"], {"main.tex": text}.get)
    bundle = select_context(
        pm, {"main.tex": text}.get, "introduction", budget_tokens=40, surrounding_lines=5
    )
    assert bundle.estimated_tokens <= 40  # never exceeds the budget
    assert any(c.kind == "section" for c in bundle.chunks)
    assert any(c.truncated for c in bundle.chunks)  # deterministic truncation
    assert any("[truncated]" in c.text for c in bundle.chunks)


def test_select_orders_sections_before_outline() -> None:  # issue 203
    text = "\\section{Introduction}\nx\n\\section{Methods}\nm\n"
    pm = build_project_map("p1", ["main.tex"], {"main.tex": text}.get)
    bundle = select_context(pm, {"main.tex": text}.get, "introduction", budget_tokens=8000)
    outline_idx = next(i for i, c in enumerate(bundle.chunks) if c.kind == "outline")
    section_idxs = [i for i, c in enumerate(bundle.chunks) if c.kind == "section"]
    assert section_idxs  # there is at least one section chunk
    # priority 0 (section) chunks all precede the priority 1 (outline) chunk.
    assert all(i < outline_idx for i in section_idxs)


def test_select_surrounding_lines_widens_window() -> None:  # issue 205
    text = "\n".join(["pre2", "pre1", "\\section{Mid}", "m1", "m2", "\\section{End}", "e"])
    pm = build_project_map("p1", ["main.tex"], {"main.tex": text}.get)
    narrow = select_context(
        pm, {"main.tex": text}.get, "mid", budget_tokens=8000, surrounding_lines=0
    )
    wide = select_context(
        pm, {"main.tex": text}.get, "mid", budget_tokens=8000, surrounding_lines=3
    )
    s0 = next(c for c in narrow.chunks if c.kind == "section").text
    s3 = next(c for c in wide.chunks if c.kind == "section").text
    assert len(s3) > len(s0)  # the larger config yields a strictly longer window
    # boundary lines outside the section appear only with the wider window.
    for boundary in ("pre1", "pre2", "\\section{End}"):
        assert boundary not in s0
        assert boundary in s3


def test_select_includes_outline_summary() -> None:
    text = "\\section{Introduction}\nx\n"
    pm = build_project_map("p1", ["main.tex"], {"main.tex": text}.get)
    bundle = select_context(pm, {"main.tex": text}.get, "introduction", budget_tokens=8000)
    assert any(c.kind == "outline" for c in bundle.chunks)
    assert estimate_tokens("abcd") == 1


# --- build_project_map ------------------------------------------------------ #


def test_project_map_stitches_inputs_and_detects_main() -> None:  # AC3
    files = {
        "main.tex": "\\documentclass{article}\n\\begin{document}\n\\input{ch1}\n\\end{document}\n",
        "ch1.tex": "\\section{Chapter One}\nbody\n",
    }
    pm = build_project_map("p1", list(files), files.get)
    assert pm.main_file == "main.tex"
    inputs = [n for n in _all(pm.outline) if n.kind == StructureKind.INPUT]
    assert inputs and inputs[0].target_path == "ch1.tex"
    assert any(c.title == "Chapter One" and c.file_path == "ch1.tex" for c in inputs[0].children)


def test_project_map_handles_cycles_and_unresolved() -> None:
    files = {
        "a.tex": "\\documentclass{x}\n\\input{b}\n",
        "b.tex": "\\input{a}\n\\input{missing}\n",
    }
    pm = build_project_map("p1", list(files), files.get)  # must not hang
    assert "missing" in pm.unresolved_inputs


def test_project_map_dedupes_unresolved_inputs() -> None:
    # spec 50 fix: the same missing target reached via several \input sites appears once.
    files = {"main.tex": "\\documentclass{a}\n\\input{missing}\n\\input{missing}\n"}
    pm = build_project_map("p1", list(files), files.get)
    assert pm.unresolved_inputs == ["missing"]


def test_project_map_caching_is_transparent() -> None:  # AC8
    files = {"main.tex": "\\documentclass{a}\n\\section{S}\nx\n"}
    first = build_project_map("p1", list(files), files.get, cache="memory")
    second = build_project_map("p1", list(files), files.get, cache="memory")
    off = build_project_map("p1", list(files), files.get, cache="off")
    assert first.content_hash == second.content_hash == off.content_hash
    assert second is first  # served from cache
    assert off.model_dump() == first.model_dump()  # identical results with/without cache


def _all(nodes):
    out = []
    for n in nodes:
        out.append(n)
        out.extend(_all(n.children))
    return out
