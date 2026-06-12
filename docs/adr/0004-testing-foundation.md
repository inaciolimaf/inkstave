# ADR 0004 — Testing foundation: test-DB strategy & the < 2-minute budget

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 04 — Testing Foundation

## Context

Inkstave has a hard rule: the **entire** test suite (unit + integration + e2e)
must run in **under 2 minutes**. This ADR records the test infrastructure and
the budget-keeping rules every later spec must follow so that adding tests never
silently blows the budget.

## Decisions

### 1. Layered tiers, default-fast

- **Backend:** `pytest` + `pytest-asyncio` (auto mode) + `httpx.AsyncClient`
  over **ASGI transport** (no sockets). Organized as `tests/unit/` (no DB/app)
  and `tests/integration/` (wired app + test DB).
- **Frontend:** `vitest` + React Testing Library + jsdom (`frontend/`).
- **E2E:** `Playwright`, a single smoke spec against a **stub** static target.
- Markers `slow`, `integration`, `e2e` are registered with `--strict-markers`;
  the default run is `-m "not slow and not e2e"`. Anything unavoidably heavy is
  marked `slow` and excluded from the default tier.

### 2. Test-DB strategy: migrate once (template) + rollback per test

- A session-scoped fixture provisions a throwaway `*_test` database and runs
  Alembic `upgrade head` **exactly once** to form the schema template
  (`TEST_DATABASE_URL`, defaulting to the compose Postgres `inkstave_test`).
- Each test gets a `db_session` opened on a connection inside an **outer
  transaction**; the `AsyncSession` uses
  `join_transaction_mode="create_savepoint"`, so endpoint/test `commit()` calls
  release SAVEPOINTs while the outer transaction is **rolled back** on teardown.
  No per-test migrations, no cross-test state.
- The engine is **function-scoped** (bound to each test's event loop) over a
  session-scoped, sync template fixture — this sidesteps pytest-asyncio
  cross-event-loop issues while keeping schema setup one-time.
- The app's `get_db_session` is overridden to share the rolled-back session, so
  endpoint writes and test assertions see the same transaction.

### 3. Fakes, never real externals

- **Redis:** `fakeredis.aioredis` injected via dependency override / `app.state`
  — no Redis process in the fast tiers.
- **Tectonic and the LLM are NEVER invoked in any test tier.** This is a hard
  rule. Slow work lives in ARQ jobs (spec 22+): the *enqueue* is asserted with a
  fake/mocked queue and the *handler body* (compile/LLM) is mocked. No real job
  runtime, no outbound network, no `sleep`s (timeouts are driven through fakes).

### 4. Factories

Hand-rolled, async-explicit factories under `tests/factories/` (a class with a
monotonic sequence + `build()` / `await create(session, ...)`), starting with
`PingFactory`. Chosen over `factory_boy` to keep async creation obvious and
dependency-light. Feature specs add their own following the same shape.

### 5. Coverage

`pytest-cov` with `branch=true`, `source=["inkstave"]`, `show_missing=true`,
and a non-aspirational `fail_under` (80%) satisfied by current code. CI emits
`coverage.xml`. The default `just test` skips coverage for speed; `just cov` and
CI add it.

### 6. CI

`.github/workflows/ci.yml` runs a **staged** job graph rather than three flat
parallel jobs. `lint` and `typecheck` run independently (no shared artifact, so
in parallel). The three test stages — `unit` (pytest unit subset + Vitest),
`integration` (Postgres 16 service; pytest integration subset + coverage), and
`e2e` (Playwright chromium smoke against docker-compose.test.yml) — each depend
only on `typecheck`, so they fan out and run concurrently. Finally the `budget`
gate depends on `[unit, integration, e2e]` and fails the build if their combined
wall-clock exceeds the 120 s budget (reusing `scripts/check_test_budget.py`,
which also scans the per-test JUnit durations the test stages upload). All pytest
stages run under `-n auto` (pytest-xdist) to hold that budget. Any failing
job fails the workflow.

## How the < 2-minute budget is maintained

1. **Template DB once + rollback per test** — never per-test migrations.
2. **Fakes for Redis**, **ASGI transport** (no sockets), **no sleeps**.
3. **Tectonic/LLM never run** — always mocked; slow bodies live in mocked ARQ
   jobs whose enqueue is asserted.
4. **Parallelism** — tiers run concurrently in CI; tests are isolation-safe
   (rollback per test) so pytest may shard too.
5. **`slow` marker** keeps any unavoidable heavy test out of the default run.
6. **Measure** — CI prints per-tier durations. Investigate any regression
   immediately; the per-tier baselines (below) are the reference.

### Measured baseline (local, this spec)

| Tier | Tests | Wall-clock |
| --- | --- | --- |
| Backend (unit + integration) | 37 | ~3 s |
| Frontend (Vitest) | 2 | ~1 s |
| E2E (Playwright smoke) | 1 | ~2 s |

Total well under the 2-minute budget, with ample headroom for feature tests.

> **Note — this is a point-in-time spec-04 baseline** (37 backend tests), captured
> at the moment the testing foundation was accepted. The suite has since grown by
> orders of magnitude (hundreds of tests). The **current** suite size, per-tier
> timings, and the pytest-xdist (`-n auto`) parallelisation strategy that keeps it
> under budget are tracked in **ADR 0053 — Performance & test speed** (spec 53),
> not here. The figures above are kept for history; do not read them as current.

## Consequences

- Every later spec adds tests by convention (these fixtures + factories) and
  must obey the budget rules above.
- New env var `TEST_DATABASE_URL` documented in `.env.example`.
- New `just` recipes: `test`, `cov`, `test-fe`, `test-e2e`, `test-all`.

## Alternatives considered

- **`create_all` instead of Alembic for the template** — faster, but running the
  real migrations also exercises them; we run migrations once, getting both.
- **DROP/CREATE schema per test** — simple but far too slow; rejected for the
  transactional-rollback pattern.
- **`factory_boy`** — heavier and awkward for async; hand-rolled factories
  chosen instead.
- **A real Redis service in CI** — unnecessary since `fakeredis` covers the
  fast tiers; omitted to keep CI lean.
