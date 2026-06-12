# Spec 04 — Testing Foundation (requirements)

## 1. Summary

This spec builds Inkstave's test infrastructure so every later spec can add
tests by convention and the **whole suite stays under 2 minutes**. It delivers:
a pytest setup (pytest-asyncio + `httpx.AsyncClient` against the ASGI app), a
fast ephemeral test-Postgres strategy (one-time migrated **template database** +
**transactional rollback per test**), a Redis fake, data **factories**, coverage
reporting, **Vitest + React Testing Library** scaffolding for the (future)
frontend, **Playwright** scaffolding for e2e (with the app stubbed where the real
thing is slow), and a **GitHub Actions** CI workflow running all tiers. It also
codifies the budget rules (no real LaTeX/LLM in tests; slow work goes to ARQ and
is mocked) that every later spec must obey.

## 2. Context & dependencies

- **Depends on:** spec 02 (app factory, settings, Redis provider, error
  envelope, `/health` `/ready`), spec 03 (async engine/session, `Base`, Alembic,
  `pings` table).
- **Unlocks:** every later spec (all tests use these fixtures/factories/CI), and
  spec 05 (refactor pass relies on a green, fast suite as its safety net).
- **Affected areas:** backend (`tests/`, `conftest.py`), frontend (Vitest config
  scaffold), infra (CI workflow), docs.

## 3. Goals

- **Backend pytest harness:**
  - `pytest`, `pytest-asyncio` (auto mode), `httpx`, `coverage`/`pytest-cov`,
    `factory_boy` (or a hand-rolled factory style), `fakeredis`.
  - A root `conftest.py` exposing reusable fixtures: `app`, `async_client`,
    `db_session`, `redis` (fake), `settings_override`.
  - An ASGI-transport `AsyncClient` fixture (no sockets) bound to `create_app()`
    with dependency overrides for DB session and Redis.
- **Fast test-DB strategy:**
  - Provision a dedicated test database, migrate it **once** to build a
    **template** (via Alembic `upgrade head` or `Base.metadata.create_all`).
  - For each test, run inside a transaction/savepoint that is **rolled back**
    afterwards (no cross-test state), avoiding per-test schema recreation.
  - The DB connection target comes from `TEST_DATABASE_URL` (defaults to the
    compose Postgres `*_test` DB / CI service container).
- **Redis fake:** `fakeredis.aioredis` injected via dependency override so no
  real Redis is needed in unit/integration tiers.
- **Factories:** a small factory layer (e.g. `tests/factories/`) starting with a
  `PingFactory`; the pattern is documented so feature specs add their own.
- **Coverage:** configured with a sensible (non-blocking-yet) threshold and an
  XML/term report; coverage runs are fast.
- **Frontend Vitest scaffold:** Vitest + React Testing Library + jsdom config
  added to `frontend/`, with one trivial passing sample test. (No app yet — the
  sample tests a pure function/util.)
- **Playwright scaffold:** Playwright config + a single smoke spec that runs
  against a **stubbed** target (e.g. a tiny static page or the app's `/health`
  served by the backend), proving the e2e tier executes without needing the full
  app or real LaTeX/LLM.
- **CI:** a GitHub Actions workflow running backend (with a Postgres + optional
  Redis service), frontend Vitest, and Playwright tiers, enforcing the suite
  passes; jobs are parallelizable.
- **Budget enforcement:** a documented, measurable strategy keeping the total
  under 2 minutes, plus a marker/convention to keep slow things out of the fast
  suite.

## 4. Non-goals (explicitly out of scope)

- Feature tests for non-existent features (only harness self-tests / samples).
- Real Tectonic compiles or real LLM/agent calls in any tier (always mocked).
- Production Docker images, deploy pipelines, migration-on-deploy (spec 56/57).
- Load/performance benchmarking tooling (spec 53 owns deeper speed work; this
  spec only establishes the budget rules and a fast baseline).
- Full Playwright coverage of user journeys (spec 54); only scaffolding + smoke.

## 5. Detailed requirements

### 5.1 Data model (if any)

None new. Tests exercise the existing `pings` table (spec 03) and create
throwaway rows that are rolled back.

### 5.2 Backend / API (if any)

#### Test layout

```
backend/
├── pyproject.toml                  # [tool.pytest.ini_options], [tool.coverage.*]
└── tests/
    ├── __init__.py
    ├── conftest.py                 # fixtures: app, async_client, db_session, redis, settings
    ├── factories/
    │   ├── __init__.py
    │   └── ping.py                 # PingFactory
    ├── unit/
    │   └── test_sample_unit.py     # e.g. settings/error/util sample
    └── integration/
        ├── test_health.py          # /health, /ready (fake redis + test db)
        └── test_db_session.py      # commit/rollback via session fixture
```

#### `[tool.pytest.ini_options]`

- `asyncio_mode = "auto"`.
- `testpaths = ["tests"]`.
- `addopts = "-q --strict-markers"`.
- Markers registered: `slow` (excluded from the default fast run), `integration`,
  `e2e`. Default selection runs unit + integration; `slow`/`e2e` are opt-in.

#### Fixtures (`conftest.py`) — required behavior

- `settings_override` — yields a `Settings` instance forced to
  `environment="test"`, `log_json=False` (readable test logs), pointing at
  `TEST_DATABASE_URL`. Installed via a `get_settings` cache clear/override so the
  app uses test settings.
- `app` — builds `create_app()` with test settings; overrides the Redis
  dependency with a `fakeredis.aioredis` client and the DB session dependency
  with the transactional test session (below). Session-scoped where safe;
  function-scoped overrides for isolation.
- `async_client` — `httpx.AsyncClient(transport=ASGITransport(app=app),
  base_url="http://test")`; function-scoped.
- **DB fixtures:**
  - Session-scoped `db_engine` against `TEST_DATABASE_URL`; **once** per session,
    ensure the schema exists by running Alembic `upgrade head` (or
    `create_all`) against the (freshly created/truncated) test DB to form the
    template.
  - Function-scoped `db_session` — open a connection, begin an outer
    transaction, bind an `AsyncSession` to it (with SAVEPOINT/nested transaction
    support), `yield`, then **roll back** the outer transaction so the DB is
    pristine for the next test. The app's `get_db_session` is overridden to use
    this same session so endpoint writes and assertions share one rolled-back
    transaction.
- `redis` — a `fakeredis.aioredis.FakeRedis()` instance; the app's `get_redis`
  override returns it; flushed between tests.

#### Factories (`tests/factories/`)

- `PingFactory` builds `Ping` instances/rows with sensible defaults
  (`note=Faker/sequence`), usable as `await PingFactory.create(db_session)` or a
  documented async pattern. Document the convention so feature specs follow it.

#### Coverage

- `[tool.coverage.run]` `source = ["inkstave"]`, `branch = true`.
- `[tool.coverage.report]` `show_missing = true`; set an initial
  `fail_under` that the current code satisfies (e.g. a modest threshold) — note
  it is non-aspirational here, just wired up.
- Produce `coverage.xml` in CI for reporting.

### 5.3 Frontend / UI (if any)

No application UI. **Test tooling scaffold only**, added to `frontend/`:

- Dev deps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`,
  `jsdom`, `@vitejs/plugin-react`, `typescript`.
- `frontend/vitest.config.ts` with `environment: "jsdom"`, a `setup` file
  importing `@testing-library/jest-dom`, and globals enabled.
- `frontend/src/lib/utils.ts` (a trivial pure function, e.g. `cn`/`sum`) plus
  `frontend/src/lib/utils.test.ts` — one passing sample test proving Vitest runs.
- `frontend/package.json` script `"test": "vitest run"` and
  `"test:watch": "vitest"`.

> The full React app (spec 09) will reuse this config; here it must run with a
> minimal `src/` containing only the sample util + test.

### 5.4 Real-time / jobs / external integrations (if any)

- **Redis:** faked via `fakeredis.aioredis` in unit/integration tiers.
- **ARQ jobs:** not implemented yet; the convention is documented — when jobs
  arrive (spec 22+), their *enqueue* is asserted with a fake/mocked queue and
  their *handler* is unit-tested in isolation; the slow body (compile/LLM) is
  mocked. No real job runtime in the fast suite.
- **Tectonic / LLM:** never invoked in tests; always mocked. State this as a
  hard rule in the ADR.

### 5.5 Configuration

- New backend dev deps (in `backend/pyproject.toml` `dev` group): `pytest`,
  `pytest-asyncio`, `pytest-cov`, `httpx`, `fakeredis`, `factory_boy` (or
  document the hand-rolled alternative), `anyio` if needed by pytest-asyncio.
- `.env.example` addition:

  | Variable | Example | Purpose |
  | --- | --- | --- |
  | `TEST_DATABASE_URL` | `postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave_test` | DB used by the test suite |

- Playwright: `frontend/playwright.config.ts` (or a top-level `e2e/` dir) with a
  single project, `testDir`, and a `webServer`/baseURL pointing at a **stub
  target** (the backend `/health` or a static fixture). Browsers installed via
  `pnpm exec playwright install --with-deps` in CI.
- **CI workflow** `infra/ci/ci.yml` (referenced from
  `.github/workflows/ci.yml`, or place it directly in `.github/workflows/`):
  - Trigger on `push` and `pull_request`.
  - **Job `backend`:** Postgres 16 service (+ optionally Redis, though fakeredis
    means it can be omitted); set `TEST_DATABASE_URL`; `uv sync`; run
    `uv run alembic upgrade head` against the test DB if the template strategy
    requires it; `uv run pytest` (excluding `slow`/`e2e`); upload coverage.
  - **Job `frontend`:** `pnpm install`; `pnpm -C frontend test`.
  - **Job `e2e`:** install Playwright browsers; run the smoke spec against the
    stub target.
  - Jobs run in parallel; the workflow fails if any tier fails.
- `justfile` additions: `just test` → run backend fast tier; `just test-fe` →
  Vitest; `just test-e2e` → Playwright smoke; `just test-all` → all three;
  `just cov` → pytest with coverage report.

### Budget-keeping strategy (must be documented in the ADR and enforced)

1. **Template DB once, rollback per test** — no per-test migrations.
2. **Fakes for Redis**, ASGI-transport client (no sockets), no `sleep`s.
3. **Tectonic and LLM never run** in tests — always mocked; slow work lives in
   ARQ jobs whose bodies are mocked and whose enqueue is asserted.
4. **Parallelism** available (pytest can shard / CI runs tiers concurrently);
   tests must be isolation-safe to allow it.
5. **A `slow` marker** keeps any unavoidable heavier test out of the default
   run; CI's default invocation excludes `slow`.
6. **Measure:** CI prints total durations; the ADR states the target (< 2 min
   wall-clock across tiers) and how to investigate regressions.

## 6. Overleaf reference (study only — never copy)

> Read for *test organization and tiering* ideas only. Overleaf uses
> Mocha/Cypress/Vitest across many services; Inkstave uses
> pytest/Vitest/Playwright. Code is written independently.

- `services/web/test/` — verified present, with subdirs `unit/`, `acceptance/`,
  `frontend/`. Study how unit vs. acceptance vs. frontend tests are separated.
  Inkstave mirrors the *separation* (`tests/unit`, `tests/integration`, e2e).
- `services/web/test/frontend/` — verified present (`bootstrap.js`,
  `reset-meta-before-each.ts`, `helpers/`). Study frontend test bootstrap and
  per-test reset. Inkstave's Vitest `setup` file is the analogue.
- `services/web/vitest.config.js` and `libraries/validation-tools/vitest.config.ts`
  — both verified present. Study Vitest configuration (environment, setup,
  globals). Inkstave authors its own `vitest.config.ts`.
- `server-ce/test/` — verified present (Cypress specs like
  `create-and-compile-project.spec.ts`, plus `cypress.config.ts`,
  `docker-compose.yml`). Study how an *end-to-end* suite is structured against a
  running stack. Inkstave uses Playwright with a stubbed target at this stage
  (full journeys in spec 54).

No Overleaf equivalent exists for: pytest fixtures, the SQLAlchemy
transactional-rollback test pattern, `fakeredis.aioredis`, or a GitHub Actions
workflow (Overleaf has no `.github/workflows/` — it uses cloudbuild). Design
those from the respective tools' docs.

## 7. Acceptance criteria

1. **Given** the backend, **when** I run `uv run pytest` from `backend/`,
   **then** all sample/harness tests pass and the run excludes `slow`/`e2e` by
   default.
2. **Given** the `async_client` fixture, **when** a test calls
   `GET /health`, **then** it returns `200` with no real socket opened (ASGI
   transport) and no real Redis/DB required for that endpoint.
3. **Given** the `redis` fixture, **when** `/ready` is called, **then**
   `checks.redis == "ok"` using the **fake** Redis (no real Redis process).
4. **Given** the `db_session` fixture, **when** a test inserts a `Ping` and the
   test ends, **then** a subsequent test sees an empty `pings` table (rollback
   isolation proven).
5. **Given** the template-DB strategy, **when** the suite runs, **then**
   migrations/schema setup happen **once per session**, not per test
   (verifiable via a counter/log or timing).
6. **Given** `PingFactory`, **when** a test creates two pings, **then** they have
   distinct ids/notes and are persisted within the rolled-back transaction.
7. **Given** the frontend scaffold, **when** I run `pnpm -C frontend test`,
   **then** the sample Vitest test passes under jsdom.
8. **Given** the Playwright scaffold, **when** I run the smoke spec against the
   stub target, **then** it passes without requiring the full app, Tectonic, or
   an LLM.
9. **Given** the CI workflow, **when** it runs on a PR, **then** the `backend`,
   `frontend`, and `e2e` jobs all execute and the workflow fails if any tier
   fails.
10. **Given** the whole default suite (backend fast tier + frontend Vitest +
    Playwright smoke), **when** measured locally/CI, **then** total wall-clock is
    **under 2 minutes**, and the ADR documents how this is maintained.
11. **Given** the rules, **when** I grep the test code, **then** there is **no**
    real Tectonic invocation and **no** real outbound LLM/network call in any
    tier.

## 8. Test plan

> This spec's "tests" are the harness self-tests plus the samples that prove each
> tier works. Feature specs bring their own feature tests later.

- **Unit (pytest):** `test_sample_unit.py` exercising a pure helper (e.g.
  settings parsing or the error envelope) to prove the unit tier runs.
- **Integration (pytest + httpx + test DB + fake Redis):**
  - `test_health.py`: `/health` 200; `/ready` 200 with fake Redis + live test
    DB; force-fail path returns 503 (DB/Redis check error injected).
  - `test_db_session.py`: insert via `PingFactory`, assert visible within the
    test, then assert isolation (empty table) in a second test.
- **Frontend unit (Vitest):** `utils.test.ts` — one passing assertion under
  jsdom.
- **E2E (Playwright):** one smoke spec hitting the stub target (e.g. the
  backend `/health` page or a static fixture) and asserting a 200 / expected
  text. No full journey here.
- **Performance/budget note:** template DB built once + transactional rollback;
  fakeredis; ASGI transport; no sleeps; CI runs tiers in parallel; `slow`/`e2e`
  excluded from the default fast run. The ADR records the measured baseline and
  the rules every later spec must follow to preserve the < 2-minute budget.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (pytest harness + fixtures, template-DB
      + rollback-per-test, fake Redis, factories, coverage, Vitest scaffold,
      Playwright scaffold, CI workflow, budget strategy).
- [ ] All acceptance criteria in §7 pass.
- [ ] All sample/harness tests in §8 written and green.
- [ ] Full default suite (all tiers) runs in < 2 minutes; measured and recorded.
- [ ] `ruff`/`mypy` clean (backend); ESLint/TS clean for the Vitest scaffold.
- [ ] `TEST_DATABASE_URL` documented in `.env.example`; ADR for the test-DB
      strategy + budget rules added under `docs/`.
- [ ] No Overleaf code copied; no real LaTeX/LLM in any test tier.
