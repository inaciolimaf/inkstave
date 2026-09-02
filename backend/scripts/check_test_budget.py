#!/usr/bin/env python3
"""Test-suite budget + slow-test gate (spec 53 §5.4 / §5.2.4).

Reads a ``test-timing.json`` and enforces the hard wall-clock budget; also scans the
slowest tests for any non-``@slow`` test over the per-test fail threshold. Pure +
fast — unit-tested in ``tests/unit/test_test_budget_gate.py`` (no real run needed).

Exit codes: 0 = pass (possibly with warnings), 1 = over budget / a slow test failed.

Usage:
    python scripts/check_test_budget.py test-timing.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class GateResult:
    ok: bool
    messages: list[str]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _total_messages(total: float) -> tuple[bool, list[str]]:
    """Gate the whole-suite wall clock against the budget + headroom alarm."""
    budget = _env_float("SUITE_BUDGET_SECONDS", 120)
    warn = _env_float("SUITE_WARN_SECONDS", 90)
    if total > budget:
        return False, [f"FAIL: suite {total:.1f}s exceeds the {budget:.0f}s budget."]
    if total > warn:
        return True, [f"WARN: suite {total:.1f}s is over the {warn:.0f}s headroom alarm."]
    return True, []


def _slow_messages(slowest: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Per-test slow scan over `slow: [{name, duration_s, slow_marked}]`."""
    slow_fail = _env_float("SLOW_TEST_FAIL_S", 10)
    slow_warn = _env_float("SLOW_TEST_WARN_S", 3)
    ok = True
    messages: list[str] = []
    for item in slowest:
        if item.get("slow_marked"):
            continue  # @slow tests are excluded from the default budget
        name = item.get("name", "?")
        dur = float(item.get("duration_s", 0))
        if dur > slow_fail:
            ok = False
            messages.append(f"FAIL: '{name}' took {dur:.1f}s (> {slow_fail:.0f}s); mark @slow.")
        elif dur > slow_warn:
            messages.append(f"WARN: '{name}' took {dur:.1f}s (> {slow_warn:.0f}s).")
    return ok, messages


def evaluate(timing: dict[str, Any]) -> GateResult:
    total = float(timing.get("total_s", 0))
    header = (
        f"Suite total: {total:.1f}s "
        f"(backend {timing.get('backend_s', 0)}s, frontend {timing.get('frontend_s', 0)}s, "
        f"e2e {timing.get('e2e_s', 0)}s)"
    )
    total_ok, total_messages = _total_messages(total)
    slow_ok, slow_messages = _slow_messages(timing.get("slowest", []))
    return GateResult(ok=total_ok and slow_ok, messages=[header, *total_messages, *slow_messages])


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: check_test_budget.py <test-timing.json>", file=sys.stderr)
        return 2
    with open(argv[1]) as fh:
        timing = json.load(fh)
    result = evaluate(timing)
    for line in result.messages:
        print(line)
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
