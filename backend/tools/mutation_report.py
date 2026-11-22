"""Scores, survivors and the Markdown report of `tools/mutation.py` (split out to keep files small)."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

MAX_SHOWN = 40
KILLED = frozenset({"killed", "timeout", "caught by type check", "segfault"})


@dataclass(frozen=True)
class Tier:
    """A group of files held to one minimum score (`[tool.mutation].tiers`)."""

    name: str
    min_score: int
    paths: tuple[str, ...]


@dataclass(frozen=True)
class Mutant:
    name: str
    path: Path
    status: str  # mutmut's: killed, survived, no tests, timeout...

    @property
    def survived(self) -> bool:
        """Not caught by a test: survived, or no selected test runs its function."""
        return self.status not in KILLED


def tier_of(path: Path, tiers: list[Tier]) -> Tier | None:
    """The first tier whose paths match `path` (fnmatch: `*` also crosses `/`)."""
    return next((t for t in tiers if any(fnmatch(str(path), p) for p in t.paths)), None)


def score(mutants: list[Mutant]) -> int:
    """Share of mutants killed, in whole percent (100 when there is nothing to kill)."""
    killed = sum(1 for m in mutants if not m.survived)
    return 100 * killed // len(mutants) if mutants else 100


def verdicts(mutants: list[Mutant], tiers: list[Tier]) -> list[tuple[Tier, int, int]]:
    """(tier, score, mutant count) of every tier that has mutants in this run."""
    out = []
    for tier in tiers:
        own = [m for m in mutants if tier_of(m.path, tiers) == tier]
        if own:
            out.append((tier, score(own), len(own)))
    return out


def report(mutants: list[Mutant], tiers: list[Tier]) -> str:
    """Markdown: score per tier against its minimum, survivors per function, the first diffs."""
    from mutmut.mutation.diff_apply import get_diff_for_mutant

    lost = [m for m in mutants if m.survived]
    untested = sum(m.status == "no tests" for m in lost)
    head = f"## Mutation testing: {score(mutants)}% killed ({len(mutants) - len(lost)}/{len(mutants)})"
    out = [head, "", f"{untested} of the {len(lost)} survivors have no test that runs their function.", ""]
    for tier, got, count in verdicts(mutants, tiers):
        mark = "ok" if got >= tier.min_score else "BELOW"
        out.append(f"- **{tier.name}**: {got}% of {count} (minimum {tier.min_score}%) {mark}")
    per_fn = Counter(m.name.split("__mutmut_")[0] for m in lost)
    out += ["", "### Survivors per function", ""]
    out += [f"- `{fn}`: {n}" for fn, n in per_fn.most_common()]
    out += ["", f"### First {min(MAX_SHOWN, len(lost))} survivors", ""]
    for m in lost[:MAX_SHOWN]:
        out += [f"`{m.name}`", "```diff", get_diff_for_mutant(m.name, path=m.path).strip(), "```"]
    return "\n".join(out)


def write_survivors(mutants: list[Mutant], target: Path) -> None:
    """Every survivor's diff, grouped by file: the to-do list for whoever writes the missing tests."""
    from mutmut.mutation.diff_apply import get_diff_for_mutant

    out = [f"# {sum(m.survived for m in mutants)} surviving mutants of {len(mutants)}", ""]
    for m in sorted((m for m in mutants if m.survived), key=lambda m: (str(m.path), m.name)):
        tag = " (no tests)" if m.status == "no tests" else ""
        out += [f"## `{m.name}`{tag}", "```diff", get_diff_for_mutant(m.name, path=m.path).strip(), "```", ""]
    target.write_text("\n".join(out), encoding="utf-8")


def publish(mutants: list[Mutant], tiers: list[Tier]) -> int:
    """Print the report (and append it to the GitHub job summary); 1 when a tier is below its minimum."""
    text = report(mutants, tiers)
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if any(got < tier.min_score for tier, got, _ in verdicts(mutants, tiers)) else 0
