# Inkstave — main commands. `make` with no target lists the commands.
#
# `make up` runs the DEV stack: everything in Docker WITH hot reload (uvicorn
# --reload on the backend, arq --watch on the worker, Vite HMR on the frontend).
# Source is bind-mounted, so code edits reload in place — no production build.
# It runs ATTACHED so all logs stream to your terminal; Ctrl+C stops it.
#
#   Browser → http://localhost:5173  (SPA, talks to the API on :8000)
#
# `make up-prod` runs the optimized PRODUCTION stack (static bundle behind nginx,
# no reload) from docker-compose.prod.yml, served on http://localhost.
#
# Both need a .env (with MIGRATE_ON_START=true so the backend migrates on boot).
#
# `make docker-up` is NOT `make up`: it starts only Postgres + Redis, for running the
# backend and the frontend on the host.
#
# CI (.github/workflows/ci.yml) runs these targets, so what passes here passes there.

.DEFAULT_GOAL := help

DEV  := docker compose -f docker-compose.dev.yml
PROD := docker compose -f docker-compose.prod.yml
E2E_INFRA := docker compose -f docker-compose.test.yml

# Overridable from the environment or the command line.
PYTHON ?= python3
TEST_DATABASE_URL ?= postgresql+asyncpg://inkstave:inkstave@localhost:$(or $(POSTGRES_PORT),5432)/inkstave_test
export TEST_DATABASE_URL

# Relative to backend/, where the recipes below run. Each path finds its own ruff config.
RUFF_PATHS := . ../scripts ../tools
# Per-tier output of the CI stages, consumed by `budget` and `coverage-combine`.
RESULTS := test-results
UNIT_MARKERS := not integration and not slow and not e2e and not live
INTEGRATION_MARKERS := integration and not slow and not e2e and not live
PLAYWRIGHT := pnpm -C frontend exec playwright test

.PHONY: help up up-d down clean build logs ps restart \
        up-prod up-prod-d down-prod clean-prod logs-prod \
        docker-up docker-down docker-logs db-test e2e-infra \
        install install-backend install-web e2e-install migrate \
        test test-unit test-integration coverage coverage-combine budget \
        lint boundaries format types docs \
        web-types web-types-check web-dev web-lint web-typecheck web-unit web-test \
        web-format web-coverage web-build web-budget e2e mobile e2e-flows e2e-smoke e2e-all

help: ## List the available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Development (hot reload) ------------------------------------------------- #

# The backend image build is slow once (Tectonic); reruns are fast.
up: ## Build + run the dev stack attached, with live logs (Ctrl+C stops it)
	$(DEV) up --build

up-d: ## Same as `up`, detached (follow with `make logs`)
	$(DEV) up -d --build

down: ## Stop the dev containers (keeps db / uploads / node_modules volumes)
	$(DEV) down

clean: ## Stop the dev containers AND wipe volumes (db, uploads, deps, cache)
	$(DEV) down -v

build: ## Build the dev images without starting
	$(DEV) build

logs: ## Follow logs from the dev stack (after `make up-d`)
	$(DEV) logs -f

ps: ## Show dev service status / health
	$(DEV) ps

restart: ## Restart the dev app services
	$(DEV) restart backend worker frontend

# --- Production (optimized build, no reload) --------------------------------- #

up-prod: ## Build + run the production stack attached (http://localhost)
	$(PROD) up --build

up-prod-d: ## Production stack, detached
	$(PROD) up -d --build

down-prod: ## Stop the production stack (keeps volumes)
	$(PROD) down

clean-prod: ## Stop the production stack AND wipe its volumes
	$(PROD) down -v

logs-prod: ## Follow production logs
	$(PROD) logs -f

# --- Infrastructure only (Postgres + Redis) ----------------------------------- #

docker-up: ## Start Postgres + Redis in the background
	docker compose up -d

docker-down: ## Stop and remove Postgres + Redis
	docker compose down

docker-logs: ## Follow logs from Postgres + Redis
	docker compose logs -f

db-test: ## Create the test database on the compose Postgres
	docker compose exec -T postgres psql -U inkstave -d postgres -c 'CREATE DATABASE inkstave_test' || true

e2e-infra: ## Start the throwaway Postgres + Redis the e2e suite uses
	$(E2E_INFRA) up -d --wait

# --- Setup -------------------------------------------------------------------- #

install: install-backend install-web ## Install backend and frontend dependencies from the lockfiles

install-backend: ## Install backend dependencies from uv.lock
	uv sync --project backend --frozen

install-web: ## Install frontend dependencies from pnpm-lock.yaml
	pnpm -C frontend install --frozen-lockfile

e2e-install: ## Install the Playwright browser the smoke tier uses
	pnpm -C frontend exec playwright install --with-deps chromium

# --- Database ----------------------------------------------------------------- #

migrate: ## Apply all pending database migrations
	uv run --project backend alembic -c backend/alembic.ini upgrade head

# --- Quality ------------------------------------------------------------------ #

test: ## Run the backend fast tier (unit + integration)
	cd backend && uv run pytest

coverage: ## Same as `test` with coverage; fails below fail_under
	cd backend && uv run pytest --cov=inkstave --cov-report=term-missing

# The two tiers below are `test` split as CI splits it. The floor applies to their sum, so
# `coverage-combine` checks it and it is switched off here.
test-unit: ## Run the backend unit tier, writing junit and coverage data
	mkdir -p $(RESULTS)
	cd backend && COVERAGE_FILE=../$(RESULTS)/unit.coverage uv run pytest -m "$(UNIT_MARKERS)" \
		--cov=inkstave --cov-report= --cov-fail-under=0 --junitxml=../$(RESULTS)/unit-junit.xml

test-integration: ## Run the backend integration tier, writing junit and coverage data
	mkdir -p $(RESULTS)
	cd backend && COVERAGE_FILE=../$(RESULTS)/integration.coverage uv run pytest -m "$(INTEGRATION_MARKERS)" \
		--cov=inkstave --cov-report= --cov-fail-under=0 --junitxml=../$(RESULTS)/integration-junit.xml

coverage-combine: ## Merge the unit + integration coverage; fails below fail_under
	cd backend && COVERAGE_FILE=../$(RESULTS)/combined.coverage uv run coverage combine --keep \
		../$(RESULTS)/unit.coverage ../$(RESULTS)/integration.coverage
	cd backend && COVERAGE_FILE=../$(RESULTS)/combined.coverage uv run coverage report
	cd backend && COVERAGE_FILE=../$(RESULTS)/combined.coverage uv run coverage xml \
		-o ../$(RESULTS)/coverage.xml --fail-under=0

budget: ## Gate the 2-minute budget (stage times in UNIT_S, INTEGRATION_S, E2E_S)
	$(PYTHON) backend/scripts/build_test_timing.py $(RESULTS) test-timing.json
	$(PYTHON) backend/scripts/check_test_budget.py test-timing.json

lint: ## Backend ruff, format check, size ceilings and import contracts
	cd backend && uv run ruff check $(RUFF_PATHS)
	cd backend && uv run ruff format --check $(RUFF_PATHS)
	uv run --project backend python scripts/lint_function_length.py
	cd backend && uv run lint-imports

boundaries: ## Import contracts only (layers, public interfaces, no cycles)
	cd backend && uv run lint-imports

format: ## Format the backend, scripts and tools
	cd backend && uv run ruff format $(RUFF_PATHS)

types: ## Type-check the backend with strict mypy
	cd backend && uv run mypy

docs: ## Check that docs/system matches the code
	uv run --project backend python -m tools.docs_coverage

# --- Frontend ------------------------------------------------------------------ #

# Building the app reads the settings; the schema does not depend on this placeholder.
web-types: ## Regenerate docs/api/openapi.json and frontend/src/api/types.ts
	JWT_SECRET=placeholder-only-to-build-the-openapi-schema uv run --project backend python backend/scripts/export_openapi.py
	pnpm -C frontend generate:api

web-types-check: web-types ## Fail if the committed API contract is out of date
	git diff --exit-code -- docs/api/openapi.json frontend/src/api/types.ts

web-dev: ## Run the Vite dev server
	pnpm -C frontend dev

web-lint: ## ESLint and the prettier check
	pnpm -C frontend lint
	pnpm -C frontend format:check

web-typecheck: ## Type-check the frontend with tsc -b
	pnpm -C frontend exec tsc -b

web-unit: ## Run the Vitest unit tests
	pnpm -C frontend test

web-test: web-lint web-typecheck web-unit ## Lint, format check, tsc -b and Vitest

web-format: ## Format the frontend with prettier
	pnpm -C frontend format

web-coverage: ## Vitest with coverage; fails below the floor in vitest.config.ts
	pnpm -C frontend test:coverage

web-build: ## Build the production bundle
	pnpm -C frontend build

web-budget: ## Fail if the initial JS of frontend/dist passes 250 KB gzip; needs a build
	node scripts/check-bundle.mjs

# The Playwright targets do not depend on web-build: the config's webServer builds the bundle
# itself, with the API URL of the e2e backend. They need `make e2e-infra` first.
e2e: ## Playwright: every route opens
	$(PLAYWRIGHT) --project=routes

mobile: ## Playwright: every route fits 390x844
	$(PLAYWRIGHT) --project=mobile

e2e-flows: ## Playwright: real journeys, without the @full tier
	$(PLAYWRIGHT) --project=flows

e2e-smoke: ## Playwright: the whole in-budget tier (what CI runs)
	$(PLAYWRIGHT) --project=smoke

e2e-all: ## Playwright: smoke plus the opt-in @full tier
	$(PLAYWRIGHT) --project=smoke --project=full
