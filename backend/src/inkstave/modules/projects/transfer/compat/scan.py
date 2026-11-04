"""Compatibility scan of an imported Overleaf template (spec 120).

The scanner is fed one file at a time, so the import never holds the whole
project in memory: :meth:`CompatScanner.feed` takes a project path and, for a
text file, its decoded content (``None`` for a binary). :meth:`CompatScanner.finish`
then resolves the file references against the paths it has seen. :func:`scan_compat`
runs the same steps over a list, for tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from inkstave.modules.projects.transfer.compat.rules import CompatRule

_COMMENT = re.compile(r"(?<!\\)%")
_TITLE = re.compile(r"\\title\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+\*?|\\\\")
# A reference may omit its extension: ``\input{chapters/intro}`` finds ``chapters/intro.tex``.
_TARGET_SUFFIXES = ("", ".tex", ".pdf", ".eps", ".png", ".jpg", ".jpeg", ".svg", ".sty", ".cls", ".bib")
_KIND_SUFFIXES = {"tex": (".tex", ".sty", ".cls", ".ltx", ".latex", ".bbx", ".cbx"), "bib": (".bib",)}
_TITLE_MAX = 255

Reference = tuple[CompatRule, str, int, str]


@dataclass(frozen=True, slots=True)
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


def _strip_comment(line: str) -> str:
    match = _COMMENT.search(line)
    return line if match is None else line[: match.start()]


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _kind_applies(rule: CompatRule, path: str) -> bool:
    """Whether a line rule covers this text file: every text file, or one kind by extension."""
    if rule.applies_to == "any":
        return True
    return _basename(path).lower().endswith(_KIND_SUFFIXES.get(rule.applies_to, ()))


def _file_rule_applies(rule: CompatRule, path: str) -> bool:
    name = _basename(path).lower()
    return name in {rule.applies_to, f".{rule.applies_to}"} and rule.pattern.search(name) is not None


def _clean_title(raw: str) -> str:
    text = _LATEX_COMMAND.sub(" ", raw).replace("{", "").replace("}", "")
    return " ".join(text.split())[:_TITLE_MAX]


class CompatScanner:
    """Accumulates findings over the files of one import."""

    def __init__(self, rules: Iterable[CompatRule]) -> None:
        self._rules = tuple(rules)
        self._findings: list[Finding] = []
        self._paths: set[str] = set()
        self._references: list[Reference] = []
        self._titles: dict[str, str] = {}

    def feed(self, path: str, text: str | None) -> None:
        """Scan one project file. ``text`` is ``None`` for a binary file."""
        self._paths.add(path)
        for rule in self._rules:
            if rule.is_file_rule and _file_rule_applies(rule, path):
                self._add(rule, path, 1, rule.message)
        if text is not None:
            self._scan_lines(path, text)

    def _scan_lines(self, path: str, text: str) -> None:
        for number, raw in enumerate(text.splitlines(), start=1):
            line = _strip_comment(raw)
            self._note_title(path, line)
            for rule in self._rules:
                if not rule.is_file_rule and _kind_applies(rule, path):
                    self._check_line(rule, path, number, line)

    def _check_line(self, rule: CompatRule, path: str, number: int, line: str) -> None:
        if "target" in rule.pattern.groupindex:
            for match in rule.pattern.finditer(line):
                self._references.append((rule, path, number, match.group("target")))
        elif rule.pattern.search(line) is not None:
            self._add(rule, path, number, rule.message)

    def _note_title(self, path: str, line: str) -> None:
        if path in self._titles or not _basename(path).lower().endswith(".tex"):
            return
        match = _TITLE.search(line)
        if match is not None:
            title = _clean_title(match.group(1))
            if title:
                self._titles[path] = title

    def _add(self, rule: CompatRule, path: str, line: int, message: str) -> None:
        self._findings.append(Finding(rule.id, rule.severity, path, line, message))

    def _resolves(self, target: str) -> bool:
        name = target.strip().removeprefix("./")
        return any(name + suffix in self._paths for suffix in _TARGET_SUFFIXES)

    def finish(self) -> list[Finding]:
        """Report every file reference that the project does not hold."""
        for rule, path, number, target in self._references:
            name = target.strip()
            if name and not self._resolves(name):
                self._add(rule, path, number, rule.message.replace("{target}", name))
        return list(self._findings)

    def title_for(self, root_path: str | None) -> str | None:
        """The ``\\title{}`` of the root document, else of the first file that has one."""
        if root_path is not None and root_path in self._titles:
            return self._titles[root_path]
        return next(iter(self._titles.values()), None)


def scan_compat(files: Iterable[tuple[str, str | None]], rules: Iterable[CompatRule]) -> list[Finding]:
    """Scan ``(path, text-or-None)`` pairs in one call. Pure: no I/O."""
    scanner = CompatScanner(rules)
    for path, text in files:
        scanner.feed(path, text)
    return scanner.finish()
