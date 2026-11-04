"""Compatibility scan of an imported Overleaf template (spec 120): pure, fixtures in memory."""

from __future__ import annotations

from pathlib import Path

from inkstave.modules.projects.transfer.compat import CompatScanner, Finding, load_compat_rules, scan_compat

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES = load_compat_rules(REPO_ROOT / "infra" / "tectonic" / "compat-rules.toml")


def _ids(findings: list[Finding]) -> list[str]:
    return [f.rule_id for f in findings]


def test_minted_reports_shell_escape_at_the_right_line() -> None:
    text = "\\documentclass{article}\n% comment\n\\usepackage[cache]{minted}\n"
    findings = scan_compat([("main.tex", text)], RULES)
    assert [(f.rule_id, f.path, f.line) for f in findings] == [("shell_escape", "main.tex", 3)]


def test_commented_out_package_is_not_reported() -> None:
    text = "% \\usepackage{minted}\n\\usepackage{graphicx}\n"
    assert scan_compat([("main.tex", text)], RULES) == []


def test_escaped_percent_does_not_hide_the_line() -> None:
    text = "100\\% sure \\usepackage{svg}\n"
    assert _ids(scan_compat([("main.tex", text)], RULES)) == ["shell_escape"]


def test_write18_and_pythontex_are_shell_escape() -> None:
    text = "\\immediate\\write18{ls}\n\\usepackage{pythontex}\n"
    assert _ids(scan_compat([("a.tex", text)], RULES)) == ["shell_escape", "shell_escape"]


def test_latexmkrc_is_reported_by_file_name_at_line_one() -> None:
    findings = scan_compat([("latexmkrc", "$pdf_mode = 1;\n"), (".latexmkrc", "")], RULES)
    assert [(f.rule_id, f.path, f.line) for f in findings] == [
        ("latexmkrc", "latexmkrc", 1),
        ("latexmkrc", ".latexmkrc", 1),
    ]


def test_latexmkrc_in_a_folder_is_reported_by_its_base_name() -> None:
    findings = scan_compat([("build/latexmkrc", "")], RULES)
    assert [(f.rule_id, f.path) for f in findings] == [("latexmkrc", "build/latexmkrc")]


def test_eps_figure_is_reported_and_other_figures_are_not() -> None:
    text = "\\includegraphics[width=3cm]{figures/plot.eps}\n\\includegraphics{a.pdf}\n"
    files = [("main.tex", text), ("figures/plot.eps", None), ("a.pdf", None)]
    findings = scan_compat(files, RULES)
    assert [(f.rule_id, f.line) for f in findings] == [("eps_figure", 1)]


def test_pdftex_primitive_and_biber_backend() -> None:
    text = "\\pdfoutput=1\n\\usepackage[backend=biber,style=numeric]{biblatex}\n"
    assert _ids(scan_compat([("main.tex", text)], RULES)) == ["pdftex_primitive", "biber_backend"]


def test_missing_file_resolves_extensions_and_subfolders() -> None:
    files = [
        ("main.tex", "\\input{chapters/intro}\n\\include{ch2}\n\\includegraphics{figures/plot.pdf}\n"),
        ("chapters/intro.tex", ""),
        ("ch2.tex", ""),
        ("figures/plot.pdf", None),
    ]
    assert scan_compat(files, RULES) == []


def test_missing_file_is_reported_with_its_line_and_target() -> None:
    findings = scan_compat([("main.tex", "intro\n\\input{gone}\n")], RULES)
    assert [(f.rule_id, f.path, f.line) for f in findings] == [("missing_file", "main.tex", 2)]
    assert (
        findings[0].message == "gone is referenced but is not in the project. The archive may be incomplete."
    )


def test_macro_driven_include_is_not_treated_as_a_missing_file() -> None:
    assert scan_compat([("main.tex", "\\input{\\jobname-body}\n")], RULES) == []


def test_binary_files_are_not_scanned_for_lines() -> None:
    assert scan_compat([("figures/plot.png", None), ("refs.bib", None)], RULES) == []


def test_title_prefers_the_root_document_then_the_first_file() -> None:
    scanner = CompatScanner(RULES)
    scanner.feed("parts/title.tex", "\\title{Part title}\n")
    scanner.feed("main.tex", "\\title{Our  Paper}\n")
    assert scanner.title_for("main.tex") == "Our Paper"
    assert scanner.title_for("missing.tex") == "Part title"
    assert scanner.title_for(None) == "Part title"


def test_title_with_nested_commands_is_not_guessed() -> None:
    scanner = CompatScanner(RULES)
    scanner.feed("main.tex", "\\title[short]{A \\textbf{Thesis}}\n")
    assert scanner.title_for("main.tex") is None


def test_no_title_when_none_is_declared() -> None:
    assert CompatScanner(RULES).title_for("main.tex") is None


def test_finding_serialises_for_the_report() -> None:
    finding = scan_compat([("main.tex", "\\usepackage{svg}")], RULES)[0]
    assert finding.as_dict() == {
        "rule_id": "shell_escape",
        "severity": "warning",
        "path": "main.tex",
        "line": 1,
        "message": finding.message,
    }
