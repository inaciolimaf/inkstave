"""scripts/check_fix_has_test.py: every `fix` commit in a range changes a test file.

Each test builds a throwaway git repository in `tmp_path`, so the checks run against real
`git log` and `git diff-tree` output without touching this repository's history.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_fix_has_test.py"
_spec = importlib.util.spec_from_file_location("check_fix_has_test", _SCRIPT)
assert _spec is not None and _spec.loader is not None
check = importlib.util.module_from_spec(_spec)
sys.modules["check_fix_has_test"] = check
_spec.loader.exec_module(check)


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty repository with a fixed identity, made the current directory."""
    for name in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(name, "Test")
    for name in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(name, "test@example.invalid")
    _git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(repo: Path, message: str, files: dict[str, str] | None = None) -> str:
    """Write `files`, commit them with `message`, and return the new commit's sha."""
    for relative, content in (files or {"src/app.py": f"# {message}\n"}).items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-F", "-", stdin=message)
    return _git(repo, "rev-parse", "HEAD").strip()


def _base(repo: Path) -> str:
    return _commit(repo, "chore: base")


@pytest.mark.parametrize(
    "path",
    [
        "backend/tests/unit/test_x.py",
        "backend/tests/conftest.py",
        "frontend/e2e/routes.spec.ts",
        "frontend/tests/router.test.ts",
        "frontend/src/modules/editor/Editor.test.tsx",
        "frontend/src/lib/format.spec.ts",
    ],
)
def test_test_files_are_recognised(path: str) -> None:
    assert check.is_test_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "backend/src/inkstave/modules/agent/service.py",
        "frontend/src/modules/editor/Editor.tsx",
        "frontend/src/lib/format.spec.tsx",
        "backend/tests_helpers.md",
        "docs/system/agent.md",
    ],
)
def test_other_files_are_not_tests(path: str) -> None:
    assert not check.is_test_file(path)


@pytest.mark.parametrize(
    ("subject", "scope"),
    [
        ("fix: stop the crash", ""),
        ("fix(agent): keep proposals", "agent"),
        ("fix(agent)!: drop the field", "agent"),
    ],
)
def test_fix_subjects_are_recognised(subject: str, scope: str) -> None:
    assert check.fix_scope(subject) == scope


@pytest.mark.parametrize(
    "subject",
    ["feat: fix the editor", "fixup! fix: stop", "fixed a bug", "fix:", "fix(agent):"],
)
def test_other_subjects_are_not_fixes(subject: str) -> None:
    assert check.fix_scope(subject) is None


def test_fix_with_a_test_file_passes(repo: Path) -> None:
    base = _base(repo)
    _commit(
        repo,
        "fix(agent): keep proposals",
        {"src/agent.py": "x = 1\n", "backend/tests/unit/test_agent.py": "def test_x(): ...\n"},
    )
    assert check.check_range(f"{base}..HEAD") == []


def test_fix_without_a_test_file_fails_and_names_the_commit(repo: Path) -> None:
    base = _base(repo)
    sha = _commit(repo, "fix(agent): keep proposals", {"backend/src/agent.py": "x = 1\n"})
    failures = check.check_range(f"{base}..HEAD")
    assert len(failures) == 1
    assert sha[:12] in failures[0]
    assert "fix(agent): keep proposals" in failures[0]
    assert "changes no test file" in failures[0]


def test_unscoped_fix_without_a_test_fails(repo: Path) -> None:
    base = _base(repo)
    _commit(repo, "fix: stop the crash", {"src/app.py": "x = 1\n"})
    assert len(check.check_range(f"{base}..HEAD")) == 1


@pytest.mark.parametrize("scope", ["deps", "docker", "ci", "deploy", "docs"])
def test_exempt_scopes_pass_without_a_test(repo: Path, scope: str) -> None:
    base = _base(repo)
    _commit(repo, f"fix({scope}): bump something", {"infra/file.yml": "a: 1\n"})
    assert check.check_range(f"{base}..HEAD") == []


def test_no_test_reason_passes(repo: Path) -> None:
    base = _base(repo)
    _commit(
        repo,
        "fix(ui): align the toolbar\n\nThe icon was a pixel off.\n\nNo-Test: pure CSS, checked by eye",
        {"frontend/src/app.css": "a {}\n"},
    )
    assert check.check_range(f"{base}..HEAD") == []


def test_empty_no_test_reason_fails(repo: Path) -> None:
    base = _base(repo)
    _commit(repo, "fix(ui): align the toolbar\n\nNo-Test:   \n", {"frontend/src/app.css": "a {}\n"})
    failures = check.check_range(f"{base}..HEAD")
    assert len(failures) == 1
    assert "empty `No-Test:` reason" in failures[0]


def test_non_fix_commits_are_not_checked(repo: Path) -> None:
    base = _base(repo)
    _commit(repo, "feat(agent): new tool", {"backend/src/agent.py": "x = 1\n"})
    _commit(repo, "chore: tidy", {"README.md": "x\n"})
    assert check.check_range(f"{base}..HEAD") == []


def test_only_offending_fix_commits_are_listed(repo: Path) -> None:
    base = _base(repo)
    _commit(repo, "fix(a): one", {"backend/src/a.py": "1\n", "backend/tests/unit/test_a.py": "2\n"})
    bad = _commit(repo, "fix(b): two", {"backend/src/b.py": "1\n"})
    failures = check.check_range(f"{base}..HEAD")
    assert len(failures) == 1
    assert bad[:12] in failures[0]


def test_a_test_file_in_an_earlier_commit_does_not_count(repo: Path) -> None:
    base = _base(repo)
    _commit(repo, "test: add a test", {"backend/tests/unit/test_x.py": "1\n"})
    _commit(repo, "fix: stop the crash", {"backend/src/x.py": "1\n"})
    assert len(check.check_range(f"{base}..HEAD")) == 1


def test_merge_commits_are_skipped(repo: Path) -> None:
    base = _base(repo)
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "fix: side fix", {"backend/tests/unit/test_side.py": "1\n"})
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "chore: main work")
    _git(repo, "merge", "-q", "--no-ff", "-m", "fix: merge with no file of its own", "side")
    assert check.check_range(f"{base}..HEAD") == []


def test_a_root_fix_is_checked_too(repo: Path) -> None:
    _commit(repo, "fix: first commit ever", {"src/app.py": "x\n"})
    failures = check.check_range("HEAD")
    assert len(failures) == 1


def test_empty_range_passes(repo: Path) -> None:
    _base(repo)
    assert check.check_range("HEAD..HEAD") == []


def test_main_returns_1_on_failure_and_0_on_success(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = _base(repo)
    _commit(repo, "fix: stop the crash", {"src/app.py": "x\n"})
    assert check.main([f"{base}..HEAD"]) == 1
    assert "must change a test file" in capsys.readouterr().out
    assert check.main(["HEAD..HEAD"]) == 0


def test_main_returns_2_when_git_cannot_read_the_range(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _base(repo)
    assert check.main(["no-such-ref..HEAD"]) == 2
    assert "git cannot read" in capsys.readouterr().err
