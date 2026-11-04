"""Load and validate ``infra/tectonic/compat-rules.toml`` (spec 120).

The rules are declarative data. A bad file fails at load with an error that names
the rule, so the worker refuses to start instead of reporting nothing.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from inkstave.core.errors import AppError

COMPAT_RULES_PATH = Path("infra/tectonic/compat-rules.toml")

SEVERITIES = frozenset({"info", "warning"})
# Scopes by file kind; any other ``applies_to`` names one bare file.
KIND_SCOPES = frozenset({"tex", "bib", "any"})


class CompatRuleError(AppError):
    """The compat-rules file is malformed. Raised at load, so startup fails."""

    status_code = 500
    error_type = "compat_rules_invalid"


@dataclass(frozen=True, slots=True)
class CompatRule:
    id: str
    severity: str
    applies_to: str
    pattern: re.Pattern[str]
    message: str

    @property
    def is_file_rule(self) -> bool:
        """A rule about the file name (``latexmkrc``), not about the lines of its content."""
        return self.applies_to not in KIND_SCOPES


def _text(raw: dict[str, Any], key: str, rule_id: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CompatRuleError(f"compat rule {rule_id!r} needs a non-empty {key!r} string.")
    return value.strip()


def _parse_rule(raw: Any, seen: set[str]) -> CompatRule:
    if not isinstance(raw, dict):
        raise CompatRuleError("Every compat rule must be a table.")
    rule_id = _text(raw, "id", "<unnamed>")
    if rule_id in seen:
        raise CompatRuleError(f"compat rule {rule_id!r} is declared twice.")
    seen.add(rule_id)
    severity = _text(raw, "severity", rule_id)
    if severity not in SEVERITIES:
        raise CompatRuleError(f"compat rule {rule_id!r} has severity {severity!r}; use info or warning.")
    applies_to = _text(raw, "applies_to", rule_id).lower()
    if "/" in applies_to or "\\" in applies_to:
        raise CompatRuleError(f"compat rule {rule_id!r} applies_to must be a file name or a kind.")
    try:
        pattern = re.compile(_text(raw, "pattern", rule_id))
    except re.error as exc:
        raise CompatRuleError(f"compat rule {rule_id!r} has an invalid pattern: {exc}") from exc
    message = _text(raw, "message", rule_id)
    return CompatRule(rule_id, severity, applies_to, pattern, message)


def parse_rules(document: dict[str, Any]) -> tuple[CompatRule, ...]:
    """Validate a decoded TOML document into rules, or raise :class:`CompatRuleError`."""
    raw_rules = document.get("rule")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CompatRuleError("The compat-rules file declares no [[rule]] tables.")
    seen: set[str] = set()
    return tuple(_parse_rule(raw, seen) for raw in raw_rules)


@lru_cache(maxsize=4)
def load_compat_rules(path: Path = COMPAT_RULES_PATH) -> tuple[CompatRule, ...]:
    """Read and validate the rules file once per process, like the package config."""
    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise CompatRuleError(f"The compat-rules file {path} does not exist.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise CompatRuleError(f"The compat-rules file {path} is not valid TOML: {exc}") from exc
    return parse_rules(document)
