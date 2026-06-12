# Spec 57 — CI/CD & First-Run Bootstrap (requirements)

## 1. Summary

This spec makes Inkstave deployable and gated. It defines a **CI pipeline**
(lint → type-check → unit → integration → e2e) that enforces the < 2-minute test
budget and a **CD/build** step that builds and (optionally) publishes the Alpine
images from spec 56. It adds **safe migrations-on-deploy** (run once, advisory
locked), a **first-run admin bootstrap** (an Overleaf-launchpad-style one-time
setup creating the initial admin), optional **seed data**, and **fail-fast
env/secret validation** at startup so a misconfigured deployment never boots.

## 2. Context & dependencies

- **Depends on:** **56** (images, compose, nginx), **04** (pytest/Vitest/
  Playwright setup, fixtures, budget, base CI), **03** (Alembic + async DB),
  **06/07** (User model, argon2 hashing) for the admin account.
- **Unlocks:** **58** (docs reference the deploy/bootstrap flows), **60** (release
  readiness verifies CI is green and < 2 min).
- **Affected areas:** infra/CI config, a small backend `bootstrap`/`cli` module,
  the app startup (settings validation + migration gate), `.env.example`.

## 3. Goals

- A CI workflow with ordered stages: **lint → type-check → unit → integration →
  e2e**, each a gate, that **fails the build if the combined test runtime
  exceeds 2 minutes**.
- A CD/build step that builds the spec-56 images, runs an image smoke job, and
  (optionally, gated by a flag/secret) tags & pushes to a registry.
- A **migration runner** that applies Alembic migrations exactly once on
  deploy/startup, safe under concurrent service starts (advisory lock), and that
  refuses to start the app if migrations are pending in strict mode.
- A **first-run bootstrap** that creates the initial admin account once and is a
  no-op thereafter (idempotent), via a CLI command and an optional guarded
  setup endpoint.
- Optional **seed data** (a demo project) behind an explicit flag, never in
  production by default.
- **Startup env/secret validation**: required vars are checked at boot; missing
  or malformed values cause an immediate, descriptive crash (fail fast).

## 4. Non-goals (explicitly out of scope)

- Writing Dockerfiles/compose/nginx (spec 56).
- Documentation prose (spec 58).
- A full admin UI, role management, or invitations (only the first admin here;
  general user management is spec 59 / future).
- Blue-green/canary deploy orchestration; cloud-provider-specific CD.
- Secret *storage* systems (Vault, KMS); this spec only **reads and validates**
  env/secret values provided to the container.

## 5. Detailed requirements

### 5.1 CI pipeline (stages)

Implement as a CI workflow (GitHub Actions assumed; if the repo uses another CI,
mirror the stages). Jobs, in order, each gating the next:

1. **lint** — `ruff check` + `ruff format --check` (backend); `eslint` +
   `prettier --check` (frontend). Fast, no services.
2. **type-check** — `mypy`/`pyright` (whichever spec 02/04 established) for
   backend; `tsc --noEmit` for frontend.
3. **unit** — `pytest` unit subset + `vitest run`. Uses fakes/mocks (fake Redis,
   no real network/LLM/Tectonic).
4. **integration** — `pytest` integration subset against an ephemeral Postgres +
   Redis (service containers) and the httpx app client. LaTeX/LLM stubbed.
5. **e2e** — Playwright (spec 54) against an app started in CI (test config,
   compiles/agent stubbed as that spec dictates).

Cross-cutting:
- **2-minute budget enforcement.** A dedicated step (or a wrapper) records the
  wall-clock of the test stages (unit + integration + e2e) and **fails** if their
  sum exceeds **120 s**. Surface the measured time in the job summary. (Lint and
  type-check are excluded from the 120 s test budget but should still be quick.)
- **Caching** of dependency installs (`uv` cache, `pnpm` store, Playwright
  browsers) keyed on lockfiles, to keep wall-clock low without affecting the
  measured *test* runtime.
- The pipeline runs on PRs and on pushes to the default branch.
- A concise pipeline diagram and stage list documented in §6-referenced ADR /
  for spec 58 to expand.

### 5.2 CD / image build step

- A workflow (or a job in the same workflow, triggered on tags / default-branch
  merges) that:
  1. Builds `inkstave-backend` and `inkstave-frontend` (spec 56 Dockerfiles).
  2. Runs the **image smoke job** from spec 56 §8 (compose up, health, `/api`,
     `/ws`, `/metrics` blocked) — this is the heavy, out-of-budget job.
  3. Asserts the image-size soft gates (spec 56 §5.8).
  4. **Optionally** tags (`:<git-sha>`, `:latest` on default branch) and pushes
     to a registry, guarded by the presence of registry credentials/secrets — if
     absent, the push step is skipped (not failed), so forks/CI without secrets
     still build.
- No deploy-to-environment step is required; document the hook point.

### 5.3 Migration runner (safe, run-once)

- A small entrypoint/CLI: `python -m app.cli migrate` (or
  `inkstave-migrate`) that runs `alembic upgrade head` programmatically.
- **Concurrency safety:** acquire a Postgres **advisory lock**
  (`pg_advisory_lock` with a fixed app-specific key) around the upgrade so that
  when `backend`, `worker`, and `collab` start simultaneously only one process
  migrates; the others wait, then proceed. Release the lock when done.
- **Deploy wiring:** the prod compose (spec 56) runs migrations via a dedicated
  one-shot `migrate` step/service (preferred) **before** app services accept
  traffic; document this. The app itself, in **strict mode**
  (`MIGRATE_ON_START=false`, the production default), checks at startup that the
  DB is at `head` and **refuses to start** otherwise with a clear error. In
  **convenience mode** (`MIGRATE_ON_START=true`, useful for single-node/dev), the
  app runs the advisory-locked upgrade itself at startup.
- Migrations must remain **forward-only and idempotent to re-run** (re-running
  `upgrade head` when already at head is a no-op); never auto-`downgrade` on
  deploy.

### 5.4 First-run admin bootstrap

A one-time setup that creates the initial admin user. Two entry points sharing
one idempotent service function `ensure_initial_admin(...)`:

- **CLI:** `python -m app.cli bootstrap-admin` — reads
  `INKSTAVE_ADMIN_EMAIL` and `INKSTAVE_ADMIN_PASSWORD` (or prompts if a TTY and
  not provided). Creates the admin if **no admin exists**; otherwise prints
  "admin already exists" and exits 0 (idempotent).
- **Guarded setup endpoint (launchpad-style):**
  `POST /api/setup/admin` — accepts `{email, password, display_name}`.
  - Returns the admin only if **zero users with the admin flag exist** (or, per
    chosen policy, zero users at all — pick and document). Once an admin exists,
    the endpoint responds `409 Conflict` / `404` (locked) forever.
  - A companion `GET /api/setup/status` reports `{needs_setup: bool}` so the
    frontend can show a first-run setup screen (the UI itself is minimal; full
    settings UI is spec 59). At least a guarded backend + a basic setup form/path
    is required so a fresh deployment is usable.
- The admin user is a normal `User` row with an `is_admin`/role flag (add the
  column + Alembic migration if not already present from earlier specs) and an
  argon2-hashed password (spec 06/07 services).
- Bootstrapping must be **safe to call repeatedly** (idempotent) and **race-safe**
  (use a unique constraint / transaction so two concurrent calls cannot create
  two admins).

### 5.5 Optional seed data

- `python -m app.cli seed --demo` creates a demo user + a sample project with a
  starter `main.tex` (and maybe a figure), for local exploration.
- Gated behind an explicit flag/command; **never** runs automatically and
  **never** in production (refuse if `ENV=production` unless `--force`).
- Idempotent: re-running does not duplicate the demo project.

### 5.6 Startup env/secret validation (fail fast)

- Centralize in the Pydantic-`Settings` (spec 02). On app/worker/collab startup,
  **before** binding ports / accepting jobs, validate that **required** vars are
  present and well-formed; on failure, log a single clear message listing the
  offending vars and **exit non-zero** immediately.
- Required in production (non-exhaustive; align with prior specs): `DATABASE_URL`,
  `REDIS_URL`, `JWT_SECRET`/keys, `OPENROUTER_API_KEY` (required only if the
  agent is enabled — gate accordingly), storage config (spec 14). Optional vars
  get documented defaults.
- Validation must distinguish **production** (strict: secrets must be set, no
  insecure defaults like a default JWT secret) from **dev/test** (lenient
  defaults allowed). Provide an explicit `ENV`/`INKSTAVE_ENV` switch.
- Provide a `python -m app.cli check-config` command that runs the same
  validation and exits 0/non-zero, usable as a pre-deploy gate and in CI.

### 5.7 Configuration

Add to `.env.example` (with comments and safe non-production defaults):
- `INKSTAVE_ENV` (`development`|`test`|`production`).
- `MIGRATE_ON_START` (default `false`).
- `INKSTAVE_ADMIN_EMAIL`, `INKSTAVE_ADMIN_PASSWORD` (documented as bootstrap-only;
  recommend unsetting after first run).
- `SEED_DEMO` (default `false`) if a flag form is used.
- Registry-related CI secrets are documented in the CI config, **not** in
  `.env.example`.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Verify paths before
> citing. Inkstave writes its own implementation.

- `server-ce/init_scripts/` — first-boot ordering: secret checks
  (`000_check_missing_secrets.sh`), secret generation
  (`100_generate_secrets.sh`), DB access check (`500_check_db_access.sh`), and
  migration run (`900_run_web_migrations.sh`). Mirror the *ordering idea*
  (validate → wait-for-DB → migrate → start) in Inkstave's own runner.
- `server-ce/services.js` — how Overleaf enumerates the processes to run. Inkstave
  instead has one process per container (spec 56); use only as background.
- `services/web/modules/launchpad/app/src/LaunchpadController.mjs` and
  `LaunchpadRouter.mjs` — the one-time first-admin setup flow (show setup when no
  admin exists, then lock). Learn the *gate-once* approach; write Inkstave's own
  `/api/setup/admin` + idempotent service.

## 7. Acceptance criteria

1. **Given** a PR, **when** CI runs, **then** stages execute in order lint →
   type-check → unit → integration → e2e, and a failing earlier stage prevents
   later stages.
2. **Given** the test stages, **when** their combined runtime exceeds 120 s,
   **then** the pipeline **fails** with the measured time reported; under 120 s it
   passes.
3. **Given** the CD workflow on a tagged/default-branch build, **when** it runs,
   **then** both Alpine images build, the image smoke job passes, size gates are
   checked, and push happens **only** when registry credentials are present
   (skipped, not failed, otherwise).
4. **Given** three app processes starting concurrently against a DB needing
   migration, **when** they boot, **then** exactly one applies the Alembic upgrade
   under an advisory lock and the others proceed without error or double-apply.
5. **Given** `MIGRATE_ON_START=false` and a DB behind `head`, **when** the app
   starts, **then** it refuses to start with a clear "pending migrations" error;
   **given** the DB at `head`, it starts normally.
6. **Given** a fresh database with no admin, **when** `bootstrap-admin` (CLI) or
   `POST /api/setup/admin` runs with valid credentials, **then** an admin user is
   created with an argon2 hash and `is_admin` set.
7. **Given** an admin already exists, **when** the bootstrap CLI runs again,
   **then** it is a no-op exiting 0; **when** `POST /api/setup/admin` is called,
   **then** it returns a locked status (409/404) and creates nothing.
8. **Given** two concurrent `POST /api/setup/admin` calls on a fresh DB, **when**
   they race, **then** at most **one** admin is created (DB constraint /
   transaction enforced).
9. **Given** `GET /api/setup/status` on a fresh vs. configured system, **then** it
   returns `needs_setup: true` then `false` after bootstrap.
10. **Given** production env with a required secret missing (e.g. no
    `JWT_SECRET`), **when** any process starts (or `check-config` runs), **then**
    it exits non-zero immediately with a message naming the missing var, and does
    not bind ports / accept jobs.
11. **Given** `seed --demo` in production without `--force`, **when** it runs,
    **then** it refuses; in development it creates exactly one demo project and is
    idempotent on re-run.

## 8. Test plan

> All listed tests are in-budget. The image build/smoke and registry push run in
> the heavy CD job (out of the 2-minute budget), as in spec 56.

- **Unit (pytest):**
  - `ensure_initial_admin` idempotency: creates once, no-ops thereafter; verifies
    `is_admin` + argon2 hash; race-safety via a unique constraint (simulate
    duplicate insert → exactly one row).
  - Settings validation: production with a missing required var raises/exits;
    dev with defaults passes; `check-config` returns correct exit codes.
  - Seed command: refuses in production, idempotent in dev.
  - Migration runner: advisory-lock acquisition is invoked; "DB not at head"
    detection returns the strict-mode refusal (mock Alembic
    `current`/`heads`).
- **Integration (pytest + httpx + test DB):**
  - `GET /api/setup/status` and `POST /api/setup/admin` lifecycle: status flips,
    second POST is locked, two concurrent POSTs yield one admin (use a
    transaction/constraint, assert single row).
  - Run the real migration runner against the test DB: `upgrade head` then a
    second run is a no-op (idempotent); concurrent-ish runs don't error.
- **E2E (Playwright):** a first-run flow — fresh app shows the setup state,
  submitting admin credentials creates the admin and unlocks login (kept minimal;
  can reuse spec 54 harness). Optional if the setup UI is backend-guarded only;
  at minimum cover via integration.
- **CI self-test:** a tiny check asserting the budget-enforcement step fails when
  fed a synthetic over-budget duration (unit-level test of the
  measurement/threshold logic), so the gate itself is verified.
- **Performance/budget note:** bootstrap/migration/config tests hit the test DB
  briefly and use mocks for Alembic internals; no network, no real images in the
  fast suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; budget-enforcement step verified.
- [ ] Full suite runs in < 2 minutes; CI gate measures and enforces it.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; ADR added under `docs/`
      (migration strategy, bootstrap mechanism, env-validation policy).
- [ ] No Overleaf code copied.
