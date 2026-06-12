# Inkstave command runner. Run `just --list` to see available recipes.
# See docs/adr/0001-tooling-choices.md for why `just` was chosen.

# Start the infrastructure services (postgres + redis) in the background.
up:
    docker compose up -d

# Stop and remove the infrastructure services.
down:
    docker compose down

# Follow logs from the running services.
logs:
    docker compose logs -f

# Format code. (Frontend prettier is added in spec 09.)
fmt:
    uv run --project backend ruff format backend
    # frontend: pnpm prettier — added in spec 09

# Lint + type-check the backend.
lint:
    uv run --project backend ruff check backend && uv run --project backend mypy backend/src

# Run the backend fast test tier (unit + integration; excludes slow/e2e).
# Parallelised with pytest-xdist (`-n auto`, inherited from pyproject addopts) so
# the day-to-day run matches the < 2-minute budget measured by `just test-timed`.
test:
    uv run --project backend pytest backend/tests

# Run the backend tests with a coverage report.
cov:
    uv run --project backend pytest backend/tests --cov=inkstave --cov-config=backend/pyproject.toml --cov-report=term-missing

# Run the frontend Vitest unit tests.
test-fe:
    pnpm -C frontend test

# Run the Playwright e2e smoke test (stub target).
test-e2e:
    pnpm -C frontend exec playwright test

# Run every test tier (backend + frontend + e2e).
test-all: test test-fe test-e2e

# Manual-only live LLM smoke (spec 67): one real OpenRouter completion. Requires a
# real OPENROUTER_API_KEY; skips (exit 0) without one. NEVER run in CI / `just test`.
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
    uv run --project backend alembic -c backend/alembic.ini upgrade head

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
