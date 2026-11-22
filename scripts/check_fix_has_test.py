#!/usr/bin/env python3
"""Fail when a `fix` commit in a git range changes no test file.

A fixed bug must not come back unnoticed, so every commit whose subject starts with
`fix` (`fix: ...` or `fix(scope): ...`) must change at least one test file. Exempt:

- the scopes `deps`, `docker`, `ci`, `deploy` and `docs`, which have no behaviour to test;
- a commit whose body has a `No-Test: <reason>` line with a non-empty reason.

A test file is any path under `backend/tests/`, `frontend/e2e/` or `frontend/tests/`, or
any file named `*.test.ts`, `*.test.tsx` or `*.spec.ts`.

    scripts/check_fix_has_test.py [RANGE]

RANGE is a git revision range, `origin/main..HEAD` by default. Merge commits are not
checked: the commits they bring in are. Exits 0 when every fix commit passes, 1 listing the
offending commits, and 2 when git cannot read the range. See CONTRIBUTING.md and CLAUDE.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass

DEFAULT_RANGE = "origin/main..HEAD"
EXEMPT_SCOPES = frozenset({"deps", "docker", "ci", "deploy", "docs"})
TEST_DIRECTORIES = ("backend/tests/", "frontend/e2e/", "frontend/tests/")
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts")
FIX_SUBJECT = re.compile(r"^fix(?:\((?P<scope>[^()\s]+)\))?!?:\s+\S")
NO_TEST_LINE = re.compile(r"^No-Test:(?P<reason>.*)$", re.MULTILINE)
RECORD_END = "\x1e"
FIELD_END = "\x1f"
LOG_FORMAT = f"%H{FIELD_END}%s{FIELD_END}%b{RECORD_END}"


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str


def git(*args: str) -> str:
    """Run git in the current directory and return its standard output."""
    result = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *args],  # noqa: S607 - git from PATH, as in the Makefile
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def list_commits(rev_range: str) -> list[Commit]:
    """Every non-merge commit in `rev_range`, oldest first."""
    output = git("log", "--no-merges", "--reverse", f"--format={LOG_FORMAT}", rev_range)
    commits: list[Commit] = []
    for record in output.split(RECORD_END):
        fields = record.strip("\n").split(FIELD_END, 2)
        if len(fields) == 3 and fields[0]:
            commits.append(Commit(sha=fields[0], subject=fields[1], body=fields[2]))
    return commits


def changed_files(sha: str) -> list[str]:
    """Paths a commit adds, changes or deletes, including those of a root commit."""
    output = git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha)
    return [line for line in output.splitlines() if line]


def fix_scope(subject: str) -> str | None:
    """The scope of a `fix` subject (`""` when it has none), or None when it is not a fix."""
    match = FIX_SUBJECT.match(subject)
    if match is None:
        return None
    return match.group("scope") or ""


def no_test_reason(body: str) -> str | None:
    """The reason of the last `No-Test:` line, possibly empty, or None when there is none."""
    reasons = [match.group("reason").strip() for match in NO_TEST_LINE.finditer(body)]
    return reasons[-1] if reasons else None


def is_test_file(path: str) -> bool:
    """True for a file the fix-test rule counts as a test."""
    return path.startswith(TEST_DIRECTORIES) or path.endswith(TEST_SUFFIXES)


def problem_with(commit: Commit, files: list[str]) -> str | None:
    """Why a fix commit is not acceptable, or None when it passes."""
    scope = fix_scope(commit.subject)
    if scope is None or scope in EXEMPT_SCOPES:
        return None
    if any(is_test_file(path) for path in files):
        return None
    reason = no_test_reason(commit.body)
    if reason is None:
        return "changes no test file (add a test, or a `No-Test: <reason>` line to the body)"
    if not reason:
        return "has an empty `No-Test:` reason"
    return None


def check_range(rev_range: str) -> list[str]:
    """One line per offending commit in `rev_range`; empty when all pass."""
    failures: list[str] = []
    for commit in list_commits(rev_range):
        problem = problem_with(commit, changed_files(commit.sha))
        if problem is not None:
            failures.append(f"  {commit.sha[:12]} {commit.subject}\n      -> {problem}")
    return failures


def main(argv: list[str]) -> int:
    rev_range = argv[0] if argv else DEFAULT_RANGE
    try:
        failures = check_range(rev_range)
    except subprocess.CalledProcessError as error:
        sys.stderr.write(f"check_fix_has_test: git cannot read {rev_range!r}: {error.stderr.strip()}\n")
        return 2
    if failures:
        sys.stdout.write(f"Fix commits in {rev_range} must change a test file:\n")
        sys.stdout.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"Every fix commit in {rev_range} changes a test file or is exempt.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
