"""AGENT_SECTION_EXTRA_COMMANDS: extra sectioning commands are sections; \\partial is not \\part."""

from __future__ import annotations

from types import SimpleNamespace

from inkstave.modules.agent.context import parse_latex_structure
from inkstave.modules.agent.context.models import StructureKind
from inkstave.modules.agent.tools.locate_section import _extra_commands


def _sections(nodes):
    out = []
    for n in nodes:
        if n.kind == StructureKind.SECTIONING:
            out.append(n)
        out.extend(_sections(n.children))
    return out


def test_extra_command_is_a_section_with_the_configured_level() -> None:
    text = "\\defsection{Opening}\nbody\n\\section{Next}\n"
    found = _sections(parse_latex_structure(text, "main.tex", extra_commands=["defsection"]))
    assert [(n.command, n.title) for n in found] == [("defsection", "Opening"), ("section", "Next")]
    assert found[0].level == 1


def test_extra_command_is_ignored_without_configuration() -> None:
    text = "\\defsection{Opening}\nbody\n"
    assert _sections(parse_latex_structure(text, "main.tex")) == []


def test_extra_name_that_prefixes_a_standard_command_does_not_hijack_it() -> None:
    text = "\\section{Intro}\n\\sec{Other}\n"
    found = _sections(parse_latex_structure(text, "main.tex", extra_commands=["sec"]))
    assert [(n.command, n.title) for n in found] == [("section", "Intro"), ("sec", "Other")]


def test_partial_is_not_a_part_section() -> None:
    text = "$\\partial x$\n\\part{Real}\n"
    found = _sections(parse_latex_structure(text, "main.tex"))
    assert [(n.command, n.title) for n in found] == [("part", "Real")]


def test_extra_commands_setting_is_split_and_trimmed() -> None:
    ctx = SimpleNamespace(settings=SimpleNamespace(agent_section_extra_commands=" defsection, ,sec ,"))
    assert _extra_commands(ctx) == ["defsection", "sec"]  # type: ignore[arg-type]
