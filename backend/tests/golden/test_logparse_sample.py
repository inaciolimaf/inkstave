"""The LaTeX-log parser against a checked-in, realistic multi-problem log (spec 27)."""

from __future__ import annotations

from inkstave.modules.compile.logparse.latex_log_parser import parse_latex_log
from inkstave.modules.compile.logparse.models import ProblemSeverity
from tests.golden.logparse_fixtures import SAMPLE_LOG


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
