# Spec 53 — Performance & Test Speed (requirements)

## 1. Summary

This spec protects the project's hard constraint — **the entire test suite (unit
+ integration + e2e) runs in under 2 minutes** — and audits runtime performance.
It delivers: test **parallelization** (pytest-xdist, Vitest worker threads), a
fast **database strategy** (per-worker template DB + per-test transaction
rollback), guarantees that **no real LaTeX/LLM/network** runs in the fast tiers,
**fixture caching**, **slow-test detection**, and a **CI gate that measures total
wall-clock and fails the build if the suite exceeds 2 minutes**. On the runtime
side it audits **DB indexes / N+1 queries**, **connection pooling**, **Redis
caching of hot endpoints**, and **WS/CRDT throughput**.

## 2. Context & dependencies

- **Depends on:** spec **04** (the testing foundation: pytest + pytest-asyncio +
  httpx, Vitest + RTL, Playwright, the per-test DB rollback fixture, and the CI
  workflow this spec extends). Practically, it audits the tests and hot paths of
  **all** prior specs.
- **Coordinates with:** spec **51** (reads `/metrics` and structured logs to find
  hot/slow paths; adds perf metrics if useful), spec **52** (the dependency audit
  and limiter must not slow tests), spec **54** (the e2e suite must fit inside the
  same 2-minute budget — this spec sets the e2e time sub-budget).
- **Unlocks:** spec **54** (e2e built against the enforced budget), spec **55**
  (refactor pass relies on the gate to catch regressions), spec **57** (CI runs
  the gate on every PR).
- **Affected areas:** backend tests/fixtures, frontend tests config, e2e config,
  infra (CI workflow, a timing script), a few runtime hot paths (indexes,
  caching), docs (perf/test ADR).

## 3. Goals

- **Parallelized backend tests:** `pytest -n auto` (pytest-xdist) with a DB
  strategy that is safe under parallelism (§5.2.1).
- **Parallelized frontend tests:** Vitest in `threads`/`forks` pool with a worker
  count tuned for CI cores.
- **Fast DB strategy:** one migrated **template database** created once per run;
  each xdist worker gets its own database cloned from the template
  (`CREATE DATABASE ... TEMPLATE ...`), and each test runs inside a transaction
  rolled back at teardown (the spec-04 fixture, now parallel-safe) (§5.2.1).
- **No slow externals in fast tiers:** LaTeX compiles, LLM calls and outbound
  network are mocked/stubbed; a guard fails the suite if a real one is attempted
  (§5.2.2).
- **Fixture caching:** session-scoped fixtures for expensive-but-immutable setup
  (engine, migrated template, compiled frontend bundle for e2e, seeded reference
  data), and reduced crypto cost in tests (argon2/JWT) (§5.2.3).
- **Slow-test detection:** `--durations` surfaced; a soft threshold flags any
  single test over a budget; a marker quarantines known-slow tests out of the
  fast tier (§5.2.4).
- **CI budget gate:** a step measures total wall-clock for the combined suite and
  **fails if > 120 s** (with headroom alarm at 90 s) (§5.4).
- **Runtime perf audit & fixes:** N+1 query detection, missing-index review,
  connection-pool sizing, Redis caching for a small set of hot read endpoints,
  and a WS/CRDT throughput sanity test (§5.5).

## 4. Non-goals (explicitly out of scope)

- Rewriting features for performance beyond the targeted, low-risk fixes
  (indexes, eager loading, a couple of cached endpoints). Big architectural perf
  work is out of scope.
- Load/stress testing infrastructure (k6/Locust pipelines), capacity planning,
  autoscaling — operator concerns.
- A real LaTeX/LLM "slow tier" that runs in normal CI. We may define an **opt-in,
  nightly** slow tier (marker `@slow`) that is **excluded** from the 2-minute
  budget and from default CI; building that nightly pipeline out fully is spec
  57's concern — here we only mark/segregate.
- Changing the approved stack or the DB engine.

## 5. Detailed requirements

### 5.1 Tiers and budget allocation

Define and document the tiers and their sub-budgets (targets, not hard per-tier
gates except the total):

| Tier | Tooling | Target | Notes |
| --- | --- | --- | --- |
| Backend unit | pytest (no DB) | fast | pure functions, schemas, helpers |
| Backend integration | pytest + test DB + fakeredis | the bulk | parallel via xdist |
| Frontend unit | Vitest + RTL | fast | threads pool |
| E2E smoke | Playwright | ≤ ~45 s | minimal representative flows (spec 54 owns content; this spec sets the time ceiling) |
| `@slow` (opt-in) | pytest/Playwright | excluded | real Tectonic/LLM; nightly only |

The **only hard gate** is total wall-clock of the default suite (all tiers except
`@slow`) **< 120 s**.

### 5.2 Test-speed requirements

#### 5.2.1 Parallel DB strategy

- At session start (once), ensure a **template DB** migrated to head via Alembic
  (cache: if it already exists and the migration head hash matches, reuse it).
- Each xdist worker (`PYTEST_XDIST_WORKER`) creates/uses a dedicated database
  cloned from the template (`CREATE DATABASE inkstave_test_gw0 TEMPLATE
  inkstave_test_tmpl`), so workers never share a DB and migrations run **once**,
  not per worker.
- Per test: open a connection, begin an outer transaction (with a SAVEPOINT/
  nested-transaction shim so code that commits is rolled back at teardown). This
  is the spec-04 fixture made xdist-safe. No `TRUNCATE`-per-test.
- Async engine: ensure pool settings don't deadlock under xdist (small pool per
  worker; `NullPool` or a tiny pool for tests is acceptable and often fastest).
- The strategy must be resilient: a clean run drops/recreates worker DBs or reuses
  them idempotently; document the choice. Keep DB count bounded by worker count.

#### 5.2.2 No real externals in fast tiers — and a guard

- **Tectonic:** the compile job is invoked via an injected runner; in fast tiers a
  **fake runner** returns a canned PDF/log without spawning Tectonic. Provide an
  autouse fixture that patches the real runner and a guard that raises if real
  `tectonic` subprocess is attempted (e.g. patch `subprocess`/the runner factory
  to assert).
- **LLM:** the OpenRouter/OpenAI client is DI'd (spec 41); fast tiers inject a
  fake/streaming-stub client. A guard fails if a real HTTP call to the LLM base
  URL is attempted (e.g. block the host via a transport stub).
- **Network:** install a global outbound-HTTP guard in the fast tier (e.g. a
  pytest fixture that patches httpx/requests transport to raise on any real
  socket, except the local test DB/Redis). This catches accidental real calls.
- **Email/notifications (spec 39):** ARQ jobs run inline/faked; SMTP is a no-op
  recorder.
- **ARQ:** jobs are executed synchronously via a test helper or an in-memory
  worker; Redis for ARQ is fakeredis or the local test instance.

#### 5.2.3 Fixture caching & cost reduction

- Session-scoped: the async engine, the migrated template DB, and (for e2e) a
  **prebuilt frontend bundle** + a single app bring-up reused across e2e specs.
- Lower crypto cost in tests: argon2 params minimal (spec 06 already exposes
  knobs); JWT signing fast; rate-limit windows short. Centralize these in the
  test settings profile.
- Cache immutable reference data builders; use factory helpers that build objects
  in-memory rather than round-tripping the DB when the DB isn't under test.
- Avoid `time.sleep` in tests — use fake clocks / awaiting conditions; ban real
  sleeps in the fast tier (a lint/grep check is acceptable).

#### 5.2.4 Slow-test detection

- Run pytest with `--durations=15` reported in CI logs.
- A small script parses the JUnit/`--durations` output and **warns** if any single
  test exceeds `SLOW_TEST_WARN_S` (default 3 s) and **fails** if any non-`@slow`
  test exceeds `SLOW_TEST_FAIL_S` (default 10 s) — pushing genuinely slow work
  behind the `@slow` marker (excluded from default CI).
- Provide markers: `@pytest.mark.slow` (and a Playwright `@slow` tag) excluded by
  default (`-m "not slow"`); these run only in the opt-in nightly tier.

### 5.3 Frontend & e2e speed

- Vitest: `pool: 'threads'` (or `forks` if needed), `poolOptions` worker count
  from CI cores; `isolate` only where required; happy-dom/jsdom chosen for speed
  where DOM is needed.
- Playwright: one shared browser context per project where safe; reuse the auth
  state via a saved storage-state (login once, reuse the token) so most specs skip
  the login UI; run with `workers` matched to CI cores; trace/video off by default
  in the fast run (on-failure only). Spec 54 defines the flows; this spec defines
  the speed constraints (stubbed LLM, mocked/precompiled Tectonic path, shared
  bring-up).

### 5.4 CI budget gate

Add a CI step (and a local `make test-timed` target) that:

1. Runs the full default suite (`-m "not slow"` for pytest, default for Vitest,
   the smoke Playwright project) and records **total wall-clock**.
2. **Fails the build if total > `SUITE_BUDGET_SECONDS` (120)**; prints a clear
   message with the measured time and the per-tier breakdown.
3. Emits a **warning** (non-failing) if total > `SUITE_WARN_SECONDS` (90) so the
   team sees the budget being approached before it breaks.
4. Writes a small machine-readable artifact (`test-timing.json`:
   `{total_s, backend_s, frontend_s, e2e_s, slowest: [...]}`) for trend tracking.

The gate measures wall-clock of the *parallel* run (what developers actually
wait), not summed CPU time. Document that the gate runs on the standard CI runner
size (record the assumed core count) so the budget is meaningful.

### 5.5 Runtime performance audit & fixes

- **N+1 detection:** add a test-time SQLAlchemy query counter (event listener on
  `before_cursor_execute`) and assert key list endpoints (project list, file
  tree, history list, collaborators) issue a **bounded** number of queries
  regardless of row count (e.g. ≤ a constant). Fix discovered N+1s with
  `selectinload`/`joinedload` or explicit joins.
- **Indexes:** review query plans for the hot lookups (by `user_id`,
  `project_id`, file `path`, history `created_at`); ensure composite indexes exist
  where the access pattern needs them; add missing ones via Alembic migrations.
  Document each added index and the query it serves.
- **Connection pooling:** set production pool size / overflow / timeout via
  settings (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`) with sane
  defaults; ensure async sessions are scoped per-request and released; verify no
  pool leaks (a test that the pool returns to baseline after N requests).
- **Redis caching of hot read endpoints:** introduce a small, explicit cache for
  a documented short list of hot, cache-safe reads (e.g. project metadata, file
  tree) with a short TTL and **explicit invalidation** on the corresponding
  writes. Cache keys namespaced by project/version; invalidation tested. Do **not**
  cache anything authz-sensitive without keying by the access decision; prefer
  caching post-authz data keyed by resource + viewer-role where needed. Keep this
  conservative — correctness over hit rate.
- **WS/CRDT throughput sanity:** a fast test that applies a burst of N Yjs updates
  through the pycrdt path and asserts they converge and complete within a small
  time bound (no real network; in-process), guarding against an accidental
  O(n²) regression. This is a smoke guard, not a benchmark.
- Optionally record `inkstave_db_query_*`/cache-hit metrics (reuse spec 51) — not
  required, but the N+1 counter should be available in tests.

### 5.6 Configuration

Add to `.env.example` / test profile:

| Var | Default | Purpose |
| --- | --- | --- |
| `SUITE_BUDGET_SECONDS` | `120` | hard CI gate |
| `SUITE_WARN_SECONDS` | `90` | early-warning threshold |
| `SLOW_TEST_WARN_S` | `3` | per-test warn |
| `SLOW_TEST_FAIL_S` | `10` | per-test fail (non-`@slow`) |
| `TEST_DB_TEMPLATE` | `inkstave_test_tmpl` | template DB name |
| `DB_POOL_SIZE` | `10` | runtime pool |
| `DB_MAX_OVERFLOW` | `5` | runtime pool overflow |
| `DB_POOL_TIMEOUT` | `30` | seconds |
| `CACHE_TTL_SECONDS` | `30` | hot-read cache TTL |
| `CACHE_ENABLED` | `true` (`false` allowed in tests that assert misses) | master switch |

`pytest.ini`/`pyproject.toml`: register the `slow` marker, set `addopts` for
xdist and durations; `vitest.config` and `playwright.config` carry the worker/
storage-state settings.

## 6. Overleaf reference (study only — never copy)

> None specific. This is general performance and test-engineering work. Do not
> copy any Overleaf code. (If you glance at Overleaf's test setup for ideas about
> acceptance-test bring-up, treat it as a textbook, not a clipboard — but it's
> Mocha/Cypress and not directly relevant.)

## 7. Acceptance criteria

1. **Given** the default suite, **when** CI runs the budget gate, **then** the
   measured total wall-clock is reported and the build **fails if it exceeds 120
   s** and warns above 90 s; a `test-timing.json` artifact is produced.
2. **Given** `pytest -n auto`, **then** the suite passes deterministically: each
   xdist worker uses its own DB cloned from a once-migrated template, migrations
   run once, and tests do not interfere across workers.
3. **Given** any fast-tier test, **when** it tries to invoke real Tectonic, a real
   LLM HTTP call, or any non-local network socket, **then** the guard raises and
   the test fails fast (proving externals are stubbed).
4. **Given** the per-test DB fixture, **then** writes a test makes are rolled back
   at teardown and the next test sees a clean state, under parallelism.
5. **Given** `--durations` output, **then** any non-`@slow` test exceeding
   `SLOW_TEST_FAIL_S` fails the slow-test check, and `@slow`-marked tests are
   excluded from the default run (`-m "not slow"`).
6. **Given** a project with many files/collaborators/history entries, **when** the
   list endpoints are queried, **then** the number of SQL queries is bounded by a
   constant (no N+1), verified by the query counter.
7. **Given** the hot read endpoints with caching enabled, **then** a repeat read
   is served from Redis (cache hit) and the corresponding write **invalidates** the
   cache so a subsequent read reflects the change.
8. **Given** N sequential requests, **then** the DB connection pool returns to its
   baseline size afterwards (no leak) and pool settings come from config.
9. **Given** a burst of N CRDT updates through the pycrdt path, **then** they
   converge to the expected document and complete within the small time bound.
10. **Given** Vitest and Playwright configs, **then** frontend units run in a
    worker pool and e2e reuses a saved auth storage-state and a single app
    bring-up (no per-spec login UI), keeping e2e within its sub-budget.
11. **Given** the whole suite locally and in CI, **then** it stays green and under
    2 minutes after these changes (no coverage meaningfully removed; any
    quarantined `@slow` test is justified in the changelog).

## 8. Test plan

> This spec's "tests" are largely the harness, guards and the gate itself. They
> must add negligible time. The whole point is the suite stays < 2 minutes.

- **Unit (pytest / Vitest):**
  - Query-counter listener counts statements; asserts a known N+1 scenario fails
    and the fixed version passes.
  - Slow-test parser flags a fixture that sleeps over the threshold (use a fake
    duration input, not a real sleep).
  - Cache helper: get/set/TTL and explicit invalidation behave; disabled mode
    bypasses.
  - External guards: attempting a patched "real" Tectonic/LLM/network call raises.
- **Integration (pytest + parallel test DB + fakeredis):**
  - xdist run across ≥2 workers passes with isolated DBs; the per-test rollback
    keeps state clean across workers.
  - Pool-leak test: run N requests, assert pool size baseline after.
  - N+1 assertions on the real list endpoints (project list, file tree, history,
    collaborators) with seeded data.
  - Cache hit + invalidation through the real endpoints.
  - CRDT burst convergence smoke (in-process pycrdt).
- **E2E (Playwright):** none new here; spec 54's smoke suite is timed by this
  spec's gate. Verify storage-state reuse halves login overhead (assert no login
  navigation in non-auth specs).
- **CI gate self-test:** a small unit test of the timing-gate script: given a
  `test-timing.json` over budget it exits non-zero; under budget, zero; in the
  warn band it warns but passes.
- **Performance/budget note:** the gate, guards and counters are microsecond-level
  in-process checks; the parallel DB strategy *reduces* total time. No real
  externals run in the measured suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full default suite runs in < 2 minutes **and the CI gate enforces it**.
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`,
      ESLint).
- [ ] New env vars documented in `.env.example`; perf/test-strategy ADR under
      `docs/`; any added indexes shipped as Alembic migrations.
- [ ] No meaningful coverage removed; any `@slow` quarantine justified in the
      changelog.
- [ ] No Overleaf code copied.
