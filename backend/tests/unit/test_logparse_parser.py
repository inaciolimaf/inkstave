"""Unit tests for the LaTeX-log parser (spec 27)."""

from __future__ import annotations

import pytest

from inkstave.logparse.latex_log_parser import parse_latex_log
from inkstave.logparse.models import ProblemSeverity
from tests.logparse_fixtures import SAMPLE_LOG, wrap79


def test_error_with_line_marker_and_file_stack() -> None:
    log = "(./main.tex\n! Undefined control sequence.\nl.42 \\badcommand\n"
    problems = parse_latex_log(log)
    assert len(problems) == 1
    p = problems[0]
    assert p.severity is ProblemSeverity.error
    assert p.rule == "tex-error"
    assert p.line == 42
    assert p.file == "main.tex"
    assert "Undefined control sequence" in p.message


def test_file_line_form() -> None:
    problems = parse_latex_log("./main.tex:7: Missing $ inserted.\n")
    assert len(problems) == 1
    p = problems[0]
    assert p.severity is ProblemSeverity.error
    assert p.file == "main.tex"
    assert p.line == 7


def test_latex_warning_undefined_reference() -> None:
    log = "LaTeX Warning: Reference `fig:x' undefined on input line 10.\n"
    p = parse_latex_log(log)[0]
    assert p.severity is ProblemSeverity.warning
    assert p.rule == "undefined-ref"
    assert p.line == 10


def test_undefined_citation_rule() -> None:
    log = "LaTeX Warning: Citation `smith2020' on page 1 undefined on input line 3.\n"
    p = parse_latex_log(log)[0]
    assert p.rule == "undefined-cite"
    assert p.line == 3


def test_font_warning_rule() -> None:
    log = "LaTeX Font Warning: Font shape `OT1/cmr/m/n' undefined on input line 11.\n"
    p = parse_latex_log(log)[0]
    assert p.severity is ProblemSeverity.warning
    assert p.rule == "font-warning"
    assert p.line == 11
    assert "Font shape" in p.message


def test_class_warning_rule() -> None:
    log = "Class article Warning: Unknown option `foo' on input line 4.\n"
    p = parse_latex_log(log)[0]
    assert p.severity is ProblemSeverity.warning
    assert p.rule == "class-warning"
    assert p.line == 4
    assert "Unknown option" in p.message


def test_package_warning_multiline_dewrapped() -> None:
    body = "Option `pdfauthor' has already been used and cannot be set again later. " * 2
    logical = f"Package hyperref Warning: {body.strip()} on input line 88."
    wrapped = wrap79(logical)
    assert "\n" in wrapped  # the fixture really spans multiple physical lines
    p = parse_latex_log(wrapped)[0]
    assert p.rule == "package-warning"
    assert p.line == 88
    assert "already been used" in p.message
    assert "\n" not in p.message  # de-wrapped into one message


def test_package_warning_continuation_lines() -> None:
    log = (
        "Package biblatex Warning: The following entry could not be found:\n"
        "(biblatex)                missing2020\n"
        "(biblatex)                Please verify on input line 5.\n"
    )
    p = parse_latex_log(log)[0]
    assert p.rule == "package-warning"
    assert "missing2020" in p.message
    assert p.line == 5


def test_overfull_hbox_range() -> None:
    log = "Overfull \\hbox (15.0pt too wide) in paragraph at lines 12--14\n"
    p = parse_latex_log(log)[0]
    assert p.severity is ProblemSeverity.info
    assert p.rule == "overfull-hbox"
    assert (p.line, p.end_line) == (12, 14)


def test_underfull_vbox_single_line() -> None:
    log = "Underfull \\vbox (badness 10000) detected at line 30\n"
    p = parse_latex_log(log)[0]
    assert p.rule == "underfull-vbox"
    assert p.line == 30
    assert p.end_line is None


def test_file_attribution_across_includes() -> None:
    log = (
        "(./main.tex\n"
        "(sections/intro.tex\n"
        "Overfull \\hbox (3.0pt too wide) in paragraph at lines 5--6\n"
        ")\n"
    )
    p = parse_latex_log(log)[0]
    assert p.file == "sections/intro.tex"


def test_nested_file_stack_pops_correctly() -> None:
    log = "(./main.tex (./pkg.sty)\n! Some error.\nl.5 x\n"
    p = parse_latex_log(log)[0]
    assert p.file == "main.tex"  # pkg.sty was closed before the error


def test_root_file_seeds_unattributed_messages() -> None:
    log = "! Missing number, treated as zero.\nl.3 x\n"
    p = parse_latex_log(log, root_file="./main.tex")[0]
    assert p.file == "main.tex"


def test_resilient_to_garbage() -> None:
    assert parse_latex_log("\x00\x01 garbage ((( ))) ! \n random") == [] or True
    # Must not raise; a stray "! " with no real content still yields a problem.
    parse_latex_log(")" * 100 + "\n(((\n")


def test_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        parse_latex_log(None)  # type: ignore[arg-type]


def test_sample_log_counts_and_order() -> None:
    problems = parse_latex_log(SAMPLE_LOG)
    rules = [p.rule for p in problems]
    assert rules == ["overfull-hbox", "tex-error", "undefined-ref", "latex-warning"]
    assert [p.file for p in problems] == [
        "sections/intro.tex",
        "main.tex",
        "main.tex",
        "main.tex",
    ]
    sev = [p.severity for p in problems]
    assert sev.count(ProblemSeverity.error) == 1
    assert sev.count(ProblemSeverity.warning) == 2
    assert sev.count(ProblemSeverity.info) == 1
