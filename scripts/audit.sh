#!/usr/bin/env bash
# Dependency vulnerability audit (spec 52 §5.6). Fails on high/critical advisories
# not in the allowlist. Wired into CI (spec 57); runs the real network audit there.
#
#   scripts/audit.sh
#
# Allowlist: one advisory id per line in scripts/audit-allowlist.txt (with a comment
# and a documented expiry). Update cadence: review weekly; bump pins on any advisory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOWLIST="${ROOT}/scripts/audit-allowlist.txt"

ignore_args=()
if [[ -f "${ALLOWLIST}" ]]; then
  while IFS= read -r line; do
    line="${line%%#*}"; line="$(echo "$line" | xargs || true)"
    [[ -n "$line" ]] && ignore_args+=(--ignore-vuln "$line")
  done < "${ALLOWLIST}"
fi

echo "==> Backend: pip-audit"
( cd "${ROOT}/backend" && uv run --with pip-audit pip-audit "${ignore_args[@]}" )

echo "==> Frontend: npm audit (fail on high+)"
( cd "${ROOT}/frontend" && npm audit --audit-level=high )

echo "==> Dependency audit passed."
