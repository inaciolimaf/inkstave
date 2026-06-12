#!/usr/bin/env bash
#
# Bring up the backend for the e2e suite (spec 54): reset the test DB to a clean,
# migrated state, then run the ARQ worker + Uvicorn together. Playwright manages
# this as a `webServer` and waits on the backend's /readyz; the trap tears the
# worker down with it so no process leaks between runs.
#
# All connection/config env (DATABASE_URL, REDIS_URL, COMPILE_MODE=mock,
# LLM_STUB=true, …) is injected by playwright.config.ts.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE/../../backend"

PY=.venv/bin
PORT="${E2E_BACKEND_PORT:-8099}"

"$PY/python" scripts/e2e_reset_db.py

"$PY/arq" inkstave.compile.worker.WorkerSettings &
WORKER=$!
"$PY/uvicorn" inkstave.main:app --host 127.0.0.1 --port "$PORT" &
SERVER=$!

cleanup() { kill "$WORKER" "$SERVER" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

# Exit (and tear everything down) as soon as either process stops.
wait -n
cleanup
