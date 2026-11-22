"""Write the ``test-timing.json`` that ``check_test_budget.py`` gates on (spec 53).

Takes the per-test durations from the JUnit files in a directory. The whole run's wall clock is
not measured here: CI's ``gate`` job measures it from the start of the run. Stdlib only on purpose:
the gate must run with a bare ``python3``.

Usage:
    python scripts/build_test_timing.py <junit-dir> <output.json>
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

SLOWEST_KEPT = 20


def _cases(path: Path) -> list[dict[str, Any]]:
    """One entry per ``<testcase>``. ``@slow`` is excluded from these runs, hence the False."""
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - JUnit files this repository's CI just wrote
    except (OSError, ET.ParseError):
        return []
    items = []
    for case in root.iter("testcase"):
        classname, name = case.get("classname", ""), case.get("name", "?")
        items.append(
            {
                "name": f"{classname}::{name}" if classname else name,
                "duration_s": float(case.get("time") or 0),
                "slow_marked": False,
            }
        )
    return items


def build_timing(junit_dir: Path) -> dict[str, Any]:
    cases = [case for path in sorted(junit_dir.glob("*.xml")) for case in _cases(path)]
    cases.sort(key=lambda case: case["duration_s"], reverse=True)
    return {"slowest": cases[:SLOWEST_KEPT]}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: build_test_timing.py <junit-dir> <output.json>", file=sys.stderr)
        return 2
    Path(argv[2]).write_text(json.dumps(build_timing(Path(argv[1]))), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
