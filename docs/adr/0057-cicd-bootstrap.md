# ADR 0057 — CI/CD & first-run bootstrap

**Status:** accepted (spec 57) · **Phase:** 7 — Hardening, packaging & docs

## Context

Inkstave needs a gated CI pipeline, a CD build for the spec-56 images, and the
deploy plumbing a fresh install requires: safe migrations, a first admin, and
fail-fast config validation. This ADR records the chosen mechanisms.

## CI pipeline (`.github/workflows/ci.yml`)

Ordered, gating stages — a failing earlier stage blocks the rest (`needs`):

```
lint → type-check → unit → integration → e2e → budget
```

- **lint** — `ruff check` + `ruff format --check` (backend); `eslint` +
  `prettier --check` (frontend).
- **type-check** — `mypy` (backend) + `tsc --noEmit` (frontend).
- **unit** — pytest `-m "not integration and not slow and not e2e"` + Vitest
  (fakes only, no real services).
- **integration** — pytest `-m "integration ..."` against an ephemeral Postgres
  service (Redis is faked).
- **e2e** — Playwright smoke (spec 54), LLM + compile stubbed, against the
  `docker-compose.test.yml` infra.
- **budget** — sums the measured wall-clock of unit + integration + e2e into a
  `test-timing.json` and runs the existing **spec-53** gate
  (`scripts/check_test_budget.py`), failing the build over 120 s. The gate's own
  logic is unit-tested in `tests/unit/test_performance.py`.

`uv`, the pnpm store and the Playwright browser are cached on lockfiles to keep
wall-clock low without affecting the *measured* test runtime. Runs on PRs and on
pushes to `main`.

## CD / image build (`.github/workflows/cd.yml`)

Out-of-budget, on `main` pushes and `v*` tags: builds both Alpine images, runs the
prod-compose **smoke** (health, `/api/health`, `/metrics` → 404, then down),
checks the spec-56 size soft-gates (warn/explain; hard-fail only >2×), and
**optionally** tags `:<sha>` / `:latest` and pushes — guarded by
`secrets.REGISTRY_USERNAME` so forks/CI without credentials *skip* (not fail) the
push. No deploy-to-environment step; the documented hook point runs
`inkstave migrate` then rolls the services.

## Migration strategy: advisory-locked, run-once

`inkstave.bootstrap.migrate.run_upgrade` takes a fixed Postgres **advisory lock**
on a dedicated sync (psycopg2) connection, then runs `alembic upgrade head`
(Alembic's async env.py uses its own connection). When `backend`, `worker` and
`collab` start together, only the lock holder migrates; the others block, then
re-run a no-op (migrations are forward-only and idempotent). Never auto-downgrade.

**Deploy wiring.** Migrations belong to a one-shot `migrate` step. The app, in
**strict mode** (`MIGRATE_ON_START=false`, the production default), checks at
startup that the DB is at head and **refuses to start** otherwise. In
**convenience mode** (`MIGRATE_ON_START=true`, single-node/dev) the app runs the
advisory-locked upgrade itself at startup.

## First-run admin bootstrap: idempotent + race-safe

`ensure_initial_admin` creates exactly the **first** admin and is a no-op once one
exists. Concurrent callers serialize on a transaction-scoped advisory lock, so two
simultaneous setups can never create two admins. Two entry points share it:

- **CLI** `python -m inkstave.cli bootstrap-admin` (reads `INKSTAVE_ADMIN_EMAIL` /
  `INKSTAVE_ADMIN_PASSWORD`, or prompts on a TTY).
- **Launchpad endpoints** at `/api/setup` (NOT versioned): `GET /api/setup/status`
  → `{needs_setup}`, `POST /api/setup/admin` creates the first admin then locks
  forever (409). Policy: *needs setup ⇔ no user carries the admin flag.*

The admin is a normal `User` row with `is_admin=true` (column already present from
earlier specs — no migration) and an argon2 hash (spec 06/07 services).

## Config validation policy: fail fast

Production guards live in `Settings` (pydantic `model_validator`s) so a
misconfigured deploy crashes at construction — spec 52 added JWT-strength + CORS;
spec 57 adds **required `DATABASE_URL` in production**. `inkstave.cli check-config`
(and `bootstrap.config_check.validate_config`) surface these as exit codes for a
pre-deploy / CI gate, plus a runtime check that the agent has a provider key in
production unless stubbed.

## Decisions / trade-offs

- **`ENVIRONMENT` reused as the env switch** (dev | test | prod) instead of adding
  a duplicate `INKSTAVE_ENV` — one source of truth (consistent with the spec-55
  de-duplication ethos). Documented in `.env.example`.
- **psycopg2-binary** added as a runtime dep purely for the migration advisory
  lock (a sync connection that spans Alembic's own async upgrade) — the simplest
  correct option without rewriting env.py.
- **Demo seed** is CLI-flag only (`seed --demo`), never an auto-run env var;
  refuses in production without `--force`; idempotent.

## Known follow-up

The frontend CI/CD jobs use `pnpm install --frozen-lockfile`, so
**`pnpm-lock.yaml` must be committed** (the spec-56 ADR notes the same gap; it
could not be regenerated in the implementation sandbox — a one-command dev-machine
fix).
