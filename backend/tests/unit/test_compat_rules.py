"""The compat-rules file is data: it loads, and a bad rule stops the load naming that rule (spec 120)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from inkstave.modules.projects.transfer.compat import CompatRuleError, load_compat_rules, parse_rules
from inkstave.modules.projects.transfer.names import default_import_name, numbered_name, reserved_safe_name
from inkstave.modules.projects.transfer.zip_import.plan import (
    ImportLimits,
    ZipSlipError,
    _classify,
    _safe_parts,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPAT_TOML = REPO_ROOT / "infra" / "tectonic" / "compat-rules.toml"

EXPECTED_IDS = {
    "shell_escape",
    "latexmkrc",
    "pdftex_primitive",
    "biber_backend",
    "eps_figure",
    "missing_file",
}


def _rule(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": "demo",
        "severity": "info",
        "applies_to": "tex",
        "pattern": "demo",
        "message": "A demo rule.",
    }
    rule.update(overrides)
    return rule


def test_compat_rules_load() -> None:
    rules = load_compat_rules(COMPAT_TOML)
    assert {rule.id for rule in rules} == EXPECTED_IDS
    assert all(rule.severity in {"info", "warning"} for rule in rules)


def test_bad_regex_fails_naming_the_rule() -> None:
    with pytest.raises(CompatRuleError, match=r"'broken'.*invalid pattern"):
        parse_rules({"rule": [_rule(id="broken", pattern="(unclosed")]})


def test_unknown_severity_fails_naming_the_rule() -> None:
    with pytest.raises(CompatRuleError, match=r"'loud'.*severity 'fatal'"):
        parse_rules({"rule": [_rule(id="loud", severity="fatal")]})


def test_duplicate_id_is_refused() -> None:
    with pytest.raises(CompatRuleError, match="'demo' is declared twice"):
        parse_rules({"rule": [_rule(), _rule()]})


def test_missing_message_is_refused() -> None:
    rule = _rule()
    del rule["message"]
    with pytest.raises(CompatRuleError, match="'demo' needs a non-empty 'message'"):
        parse_rules({"rule": [rule]})


def test_applies_to_must_not_be_a_path() -> None:
    with pytest.raises(CompatRuleError, match="applies_to"):
        parse_rules({"rule": [_rule(applies_to="figures/latexmkrc")]})


def test_no_rules_is_refused() -> None:
    with pytest.raises(CompatRuleError, match="no \\[\\[rule\\]\\]"):
        parse_rules({})


def test_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    load_compat_rules.cache_clear()
    with pytest.raises(CompatRuleError, match="does not exist"):
        load_compat_rules(tmp_path / "absent.toml")


def test_numbered_name_keeps_the_extension() -> None:
    assert numbered_name("Intro.tex", 2) == "Intro (2).tex"
    assert numbered_name("README", 3) == "README (3)"
    assert numbered_name(".gitignore", 2) == ".gitignore (2)"


def test_reserved_name_gets_an_underscore_before_the_extension() -> None:
    assert reserved_safe_name("con.tex") == "con_.tex"
    assert reserved_safe_name("NUL") == "NUL_"


def test_default_import_name_is_the_stem_or_a_fallback() -> None:
    assert default_import_name("My Thesis.zip") == "My Thesis"
    assert default_import_name(None) == "Imported project"


def test_template_renames_reserved_device_names() -> None:
    assert _safe_parts("figs/con.tex", template=True) == ("figs", "con_.tex")


def test_plain_zip_still_rejects_reserved_device_names() -> None:
    with pytest.raises(ZipSlipError):
        _safe_parts("con.tex")


def test_template_still_rejects_traversal() -> None:
    with pytest.raises(ZipSlipError):
        _safe_parts("../con.tex", template=True)


def test_latexmkrc_is_text_only_for_a_template() -> None:
    limits = ImportLimits(1, 1, 1, 1, frozenset(), template=True)
    assert _classify("latexmkrc", limits) == "text"
    assert _classify("latexmkrc", ImportLimits(1, 1, 1, 1, frozenset())) is None
