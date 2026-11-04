"""The compat-rules file is found whatever the working directory (spec 120; the e2e backend runs from backend/)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.modules.projects.transfer.compat import rules


def test_rules_found_from_the_backend_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(rules.__file__).resolve().parents[7]
    monkeypatch.chdir(repo_root / "backend")
    path = rules._default_rules_path()
    assert path.is_file()
    assert rules.load_compat_rules(path)


def test_rules_found_from_the_repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(rules.__file__).resolve().parents[7]
    monkeypatch.chdir(repo_root)
    assert rules._default_rules_path() == Path("infra/tectonic/compat-rules.toml")
