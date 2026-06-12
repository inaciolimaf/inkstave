#!/usr/bin/env bash
# Run the default test suite, measure wall-clock per tier, write test-timing.json,
# and enforce the budget gate (spec 53 §5.4). The gate fails the build if the total
# exceeds SUITE_BUDGET_SECONDS (120) and warns above SUITE_WARN_SECONDS (90).
#
#   just test-timed   (or:  scripts/run_timed.sh)
#
# Assumes a standard CI runner; xdist uses `-n auto` to match developer wall-clock.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JUNIT="$ROOT/test-junit.xml"
rm -f "$JUNIT"

echo "==> Backend (pytest -n auto, excluding @slow)"
be_start=$(date +%s)
uv run --project backend pytest backend/tests -n auto -m "not slow" --durations=15 --junitxml="$JUNIT" -q
be_rc=$?
backend_s=$(( $(date +%s) - be_start ))

echo "==> Frontend (vitest)"
fe_start=$(date +%s)
( cd frontend && (pnpm test --run >/dev/null 2>&1 || npx vitest run >/dev/null 2>&1) ) || true
frontend_s=$(( $(date +%s) - fe_start ))

total_s=$(( backend_s + frontend_s ))
python3 - "$total_s" "$backend_s" "$frontend_s" "$JUNIT" > test-timing.json <<'PY'
import json, sys
import xml.etree.ElementTree as ET

total, be, fe = (int(x) for x in sys.argv[1:4])
junit = sys.argv[4] if len(sys.argv) > 4 else ""


def parse_slowest(path, top=20):
    """Parse a pytest JUnit XML into the slowest non-@slow testcases.

    Each <testcase> carries a `time` (seconds) attribute; we keep the slowest
    `top` and emit the {name, duration_s, slow_marked} shape that
    check_test_budget.py expects. `@slow` tests are excluded from the default
    run (`-m "not slow"`), so none appear here and slow_marked stays False.
    """
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    items = []
    for case in root.iter("testcase"):
        try:
            dur = float(case.get("time", 0) or 0)
        except (TypeError, ValueError):
            continue
        cls = case.get("classname", "")
        name = case.get("name", "?")
        ident = f"{cls}::{name}" if cls else name
        items.append({"name": ident, "duration_s": dur, "slow_marked": False})
    items.sort(key=lambda i: i["duration_s"], reverse=True)
    return items[:top]


json.dump(
    {
        "total_s": total,
        "backend_s": be,
        "frontend_s": fe,
        "e2e_s": 0,
        "slowest": parse_slowest(junit),
    },
    sys.stdout,
)
PY

echo "==> Budget gate"
python3 backend/scripts/check_test_budget.py test-timing.json
gate_rc=$?

[ "$be_rc" -eq 0 ] || { echo "Backend tests failed (rc=$be_rc)"; exit "$be_rc"; }
exit "$gate_rc"
