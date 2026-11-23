"""Mutation testing on the functions a change touched, on every core, scored per tier.

Usage (from backend/):

    uv run python -m tools.mutation                  # functions changed since origin/main
    uv run python -m tools.mutation --base HEAD~3    # ... since another ref
    uv run python -m tools.mutation src/inkstave/x.py  # every function of these files
    uv run python -m tools.mutation --all --survivors s.md  # every file in scope + each survivor's diff
    uv run python -m tools.mutation --check-speed    # only the 5 s budget of the tests

Only files matching `[tool.mutation].paths` (the pure code) are mutated, and only the unit tests of
`[tool.mutmut]` run (at most `max-test-seconds` in one process). A mutant of a function no selected
test runs ("no tests") counts as a survivor: counting it as killed would score untested code at 100%.
Exit 1 when a tier scores below its minimum or the tests pass their budget.
`MUTATION_WORKERS` sets the number of mutmut processes (default: every core).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from tools.mutation_report import Mutant, Tier, publish, write_survivors

ROOT = Path(__file__).resolve().parent.parent
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
PYTEST_TIME = re.compile(r" in ([\d.]+)s")
NO_TEST_RUNS_IT = "Stopping early, because we could not find any test case"
NOT_RUN = frozenset({"skipped", "check was interrupted by user"})


def changed_lines(base: str, roots: list[str]) -> dict[Path, set[int]]:
    """Lines added or changed under `roots` since the merge base with `base` (working tree included)."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    out: dict[Path, set[int]] = {}
    for chunk in _git("diff", "-U0", "--relative", merge_base, "--", *roots).split("\ndiff --git ")[1:]:
        name = re.search(r"^\+\+\+ b/(\S+)$", chunk, re.MULTILINE)
        if not name or not name.group(1).endswith(".py"):
            continue
        lines = out.setdefault(Path(name.group(1)), set())
        for start, count in HUNK.findall(chunk):
            lines.update(range(int(start), int(start) + int(count or 1)))
    return out


def _git(*args: str) -> str:
    cmd = ["git", *args]  # fixed executable, arguments built here
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout  # noqa: S603


def mutant_globs(path: Path, lines: set[int] | None) -> list[str]:
    """mutmut name patterns of the functions in `path` that overlap `lines` (all when None).

    mutmut mutates module-level functions (`x_name`) and methods (`xǁClassǁname`).
    """
    # mutmut names modules from the package root: src/inkstave/x.py is `inkstave.x`.
    module = ".".join(path.with_suffix("").parts[1:])
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    globs = []
    for prefix, fn in _functions(tree):
        if lines is None or lines & set(range(fn.lineno, (fn.end_lineno or fn.lineno) + 1)):
            globs.append(f"{module}.{prefix}{fn.name}__mutmut_*")
    return globs


def _functions(tree: ast.Module) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.append(("x_", node))
        elif isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
            found += [(f"xǁ{node.name}ǁ", m) for m in methods]
    return found


def workers() -> int:
    """mutmut's process count: `MUTATION_WORKERS`, else every core."""
    return int(os.environ.get("MUTATION_WORKERS") or os.cpu_count() or 4)


def run_mutmut(files: list[Path], globs: list[str], marker_args: list[str]) -> None:
    """Run mutmut in this process with `only_mutate` narrowed to `files` (not settable from the CLI).

    `mutants/` starts empty: mutmut treats a file it copied unmutated on an earlier run as
    "unmodified" and would skip it now that it is in `only_mutate`.
    """
    from mutmut import __main__ as main_module
    from mutmut import configuration  # mutmut is imported only when there is work to do

    os.chdir(ROOT)
    shutil.rmtree(ROOT / "mutants", ignore_errors=True)
    configuration.config().only_mutate = [str(f) for f in files]
    configuration.config().pytest_add_cli_args_test_selection += marker_args
    said = _listen_to(main_module)
    try:
        main_module._run(globs, max_children=workers())
    except SystemExit:
        # mutmut also exits when no selected test runs any mutated function; then every mutant stays
        # "not checked" and collect() counts it as "no tests". Any other exit (a test failing inside
        # mutants/, a failing clean run) is a broken run, not a score.
        if not any(line.startswith(NO_TEST_RUNS_IT) for line in said):
            raise


def _listen_to(module: object) -> list[str]:
    """Copy of what `module` prints: mutmut says why it stopped only in text."""
    said: list[str] = []

    def tee(*args: object, **kwargs: Any) -> None:
        said.append(" ".join(map(str, args)))
        print(*args, **kwargs)

    module.print = tee  # type: ignore[attr-defined]  # module globals shadow the builtin
    return said


@dataclass(frozen=True)
class Settings:
    """`[tool.mutation]` and `[tool.mutmut]` in `pyproject.toml`."""

    paths: tuple[str, ...]
    test_paths: list[str]  # [tool.mutmut].pytest_add_cli_args_test_selection
    pytest_args: list[str]  # [tool.mutmut].pytest_add_cli_args (ignores, plugins off)
    roots: list[str]  # [tool.mutmut].source_paths
    test_selection: str  # a pytest -m expression; empty selects every test under test_paths
    max_test_seconds: float
    tiers: list[Tier]

    def marker_args(self) -> list[str]:
        return ["-m", self.test_selection] if self.test_selection else []


def load_settings() -> Settings:
    with open(ROOT / "pyproject.toml", "rb") as fh:
        tool = tomllib.load(fh)["tool"]
    raw = tool["mutation"]
    mutmut = tool["mutmut"]
    tests = list(mutmut.get("pytest_add_cli_args_test_selection", ["tests/"]))
    args, roots = list(mutmut.get("pytest_add_cli_args", [])), list(mutmut["source_paths"])
    tiers = [Tier(t["name"], int(t["min-score"]), tuple(t["paths"])) for t in raw["tiers"]]
    selection, budget = raw.get("test-selection", ""), float(raw["max-test-seconds"])
    return Settings(tuple(raw["paths"]), tests, args, roots, selection, budget, tiers)


def test_seconds(settings: Settings) -> float:
    """How long the tests mutmut runs take in one process, by pytest's own clock, on a warm run.

    mutmut runs them again and again, so the first run's cost (bytecode, a cold disk cache: about
    half the time on a fresh CI runner) is paid once; a first run warms up and is not counted.
    """
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider"]
    cmd += ["-o", "addopts=", *_extra(settings.pytest_args), *settings.marker_args(), *settings.test_paths]
    subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=300, check=False)  # noqa: S603
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, check=False)  # noqa: S603
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    found = PYTEST_TIME.search(last)
    if done.returncode != 0 or not found:
        raise SystemExit(f"The tests mutmut runs failed:\n{done.stdout[-3000:]}{done.stderr[-2000:]}")
    return float(found.group(1))


def _extra(args: list[str]) -> list[str]:
    """The mutmut pytest arguments the measure does not already pass."""
    return [a for a in args if a.startswith("--ignore") or a.startswith("--deselect")]


def check_speed(settings: Settings) -> bool:
    """True when the selected tests fit their budget; prints the measure either way."""
    took = test_seconds(settings)
    ok = took <= settings.max_test_seconds
    verdict = "ok" if ok else "OVER: make them faster or move the slow ones out of the selection"
    budget = f"{took:.2f} s of {settings.max_test_seconds:g} s"
    tests = settings.test_paths
    paths = tests if len(tests) <= 3 else [f"{len(tests)} test files"]
    which = " ".join([*settings.marker_args(), *paths])
    print(f"Tests for mutation ({which}): {budget}, {verdict}")
    return ok


def collect(globs: list[str]) -> list[Mutant]:
    """Every tested mutant of the functions in `globs`, read from `mutants/`."""
    from mutmut.mutation.data import SourceFileMutationData
    from mutmut.stats import status_by_exit_code
    from mutmut.utils.file_utils import walk_mutatable_files

    found = []
    for path in walk_mutatable_files():
        data = SourceFileMutationData(path=path)
        data.load()
        for name, code in data.exit_code_by_key.items():
            status = "no tests" if code is None else status_by_exit_code[code]
            if status not in NOT_RUN and _matches(name, globs):
                found.append(Mutant(name, Path(path), status))
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("files", nargs="*", type=Path, help="mutate every function of these files")
    parser.add_argument("--base", default="origin/main", help="diff against the merge base with REF")
    parser.add_argument("--all", action="store_true", help="mutate every file in [tool.mutation].paths")
    parser.add_argument("--survivors", type=Path, help="also write every survivor's diff to this file")
    parser.add_argument("--check-speed", action="store_true", help="only check the tests' time budget")
    args = parser.parse_args(argv)
    settings = load_settings()
    if not check_speed(settings):
        return 1
    if args.check_speed:
        return 0
    files = _all_files(settings.paths) if args.all else args.files
    targets = _targets(files, args.base, settings)
    globs = [g for path, lines in targets.items() for g in mutant_globs(path, lines)]
    if not globs:
        print("No function in [tool.mutation].paths changed: nothing to mutate.")
        return 0
    print(f"Mutating {len(globs)} function(s) in {len(targets)} file(s).", flush=True)
    run_mutmut(list(targets), globs, settings.marker_args())
    mutants = collect(globs)
    if args.survivors:
        write_survivors(mutants, args.survivors)
    return publish(mutants, settings.tiers)


def _targets(files: list[Path], base: str, settings: Settings) -> dict[Path, set[int] | None]:
    """Whole files given on the command line, or the changed lines of the files under `paths`."""
    if files:
        return dict.fromkeys(files)
    changed = changed_lines(base, settings.roots)
    return {f: lines for f, lines in changed.items() if _in_scope(f, settings.paths)}


def _in_scope(path: Path, paths: tuple[str, ...]) -> bool:
    return any(fnmatch(str(path), p) for p in paths)


def _all_files(paths: tuple[str, ...]) -> list[Path]:
    """Every Python file `[tool.mutation].paths` matches."""
    found = {p.relative_to(ROOT) for pattern in paths for p in ROOT.glob(pattern) if p.suffix == ".py"}
    return sorted(found)


def _matches(name: str, globs: list[str]) -> bool:
    return any(name.startswith(g.removesuffix("*")) for g in globs)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
