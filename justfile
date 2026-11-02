# Inkstave command runner. Run `just --list` to see available recipes.
# The Makefile is the source of truth (`make` lists it); recipes with an equivalent delegate.
# `just up/down/logs` are the infra-only `make docker-up/down/logs`, NOT `make up/down/logs`.
# See docs/adr/0001-tooling-choices.md for why `just` was chosen.

# Start the infrastructure services (postgres + redis) in the background.
up:
    make docker-up

# Stop and remove the infrastructure services.
down:
    make docker-down

# Follow logs from the running services.
logs:
    make docker-logs

# Format the backend. (`make web-format` formats the frontend.)
fmt:
    make format

# Lint + type-check the backend. `ruff check` enforces the complexity budget
# (C901 / PLR09xx) and the bandit security rules; the function-length ceiling
# has no ruff equivalent, so it ships as its own dependency-free checker.
lint:
    make lint types

# Run the backend fast test tier (unit + integration; excludes slow/e2e).
# Parallelised with pytest-xdist (`-n auto`, inherited from pyproject addopts) so
# the day-to-day run matches the < 2-minute budget measured by `just test-timed`.
test:
    make test

# Run the backend tests with a coverage report.
cov:
    make coverage

# Run the frontend Vitest unit tests.
test-fe:
    make web-unit

# Run the Playwright e2e suite (smoke + @full).
test-e2e:
    make e2e-all

# Run every test tier (backend + frontend + e2e).
test-all: test test-fe test-e2e

# Manual-only live LLM smoke (spec 67): one real completion. Requires the configured
# provider's real API key; skips (exit 0) without one. NEVER run in CI / `just test`.
agent-live:
    uv run --project backend python backend/scripts/agent_live_smoke.py

# Run the FastAPI app locally with autoreload (development).
dev:
    uv run --project backend uvicorn inkstave.main:app --reload --app-dir backend/src

# Run the FastAPI app without autoreload (prod-like).
run:
    uv run --project backend uvicorn inkstave.main:app --app-dir backend/src

# Apply all pending database migrations.
migrate:
    make migrate

# Autogenerate a new migration from model changes: just makemigration name="..."
makemigration name:
    uv run --project backend alembic -c backend/alembic.ini revision --autogenerate -m "{{name}}"

# Roll back the most recent migration.
downgrade:
    uv run --project backend alembic -c backend/alembic.ini downgrade -1

# Diagnose the environment: config validity + Postgres/Redis reachability (spec 62).
doctor:
    uv run --project backend python -m inkstave.cli doctor

# Prepare a fresh checkout: create .env, sync Python deps, install JS deps.
# (Frontend install is a no-op until spec 09 adds deps; never fails if idle.)
bootstrap:
    cp -n .env.example .env || true
    uv sync --project backend
    pnpm install || true

# Install the git pre-commit hooks.
hooks:
    uv run --project backend pre-commit install

# Run the default suite, measure wall-clock, and enforce the < 2-minute budget gate.
test-timed:
    scripts/run_timed.sh

# Open the local Mailpit inbox (dev). Mailpit must be up
# (docker compose -f docker-compose.dev.yml up).
mail:
    @echo "Mailpit inbox: http://localhost:8025"
    -xdg-open http://localhost:8025 >/dev/null 2>&1 || true
