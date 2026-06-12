# ADR 0053 — Performance & test speed

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 53 — Performance & Test Speed (Phase 7)

## Context

The project's hard constraint is that the whole default test suite runs in **under
2 minutes**. This ADR records the tiers, the parallel strategy, the externals guards,
the CI budget gate, and the targeted runtime perf fixes.

## Decisions

### 1. Tiers and the single hard gate

Backend unit / backend integration (test DB + fakeredis) / frontend unit (Vitest) /
e2e smoke (Playwright, ≤ ~45 s, spec 54) / `@slow` (opt-in nightly, excluded). The
**only** hard gate is total wall-clock of the default suite (`-m "not slow"`)
**< 120 s**, with a 90 s headroom warning.

### 2. Parallel backend tests, per-worker DB

Tests run under `pytest -n auto` (pytest-xdist). Each worker uses its **own database**
suffixed by `PYTEST_XDIST_WORKER` (`inkstave_test_gw0`, …) — set once in
`_configure_test_env` so the worker's Alembic migration, engine, and app all use it.
Workers never share state; the existing savepoint-rollback `db_session` keeps each test
isolated. **Trade-off:** each worker migrates its own DB rather than cloning a single
once-migrated template via `CREATE DATABASE … TEMPLATE`. Per-worker migration is a few
fast `alembic upgrade`s and avoids cross-process template-build coordination (advisory
locks / sentinels); it was chosen for robustness, and the measured wall-clock fell from
~60 s (single-process) to **~21 s** with `-n auto`. xdist requires deterministic
collection — a `test_requires_auth` parametrize that used `uuid4()` was made to use
fixed ids.

### 3. No real externals in the fast tier — guards

- **Tectonic:** the existing autouse `_no_real_compile` replaces the runner with a loud
  failure (smoke tier sets `RUN_REAL_COMPILE=1`).
- **LLM:** DI'd `FakeLLM` in tests; no real client is constructed.
- **Network:** a new autouse `_no_real_network` patches `socket.getaddrinfo` to raise on
  any non-local hostname, so an accidental real HTTP/LLM call fails fast; localhost / IP
  literals (the test DB, fakeredis) stay reachable.

### 4. Slow-test detection + CI budget gate

`pytest --durations=15` is on by default. `scripts/check_test_budget.py` reads a
`test-timing.json` and (a) fails over `SUITE_BUDGET_SECONDS`, warns over
`SUITE_WARN_SECONDS`; (b) fails any non-`@slow` test over `SLOW_TEST_FAIL_S`, warns over
`SLOW_TEST_WARN_S`. `scripts/run_timed.sh` (`just test-timed`) measures per-tier
wall-clock, writes `test-timing.json`, and runs the gate. The gate logic is unit-tested
with synthetic timing (no real run).

### 5. Runtime perf fixes (targeted, low-risk)

- **N+1:** the session-scoped `query_counter` (event listener) asserts the file-tree
  read issues a bounded query count regardless of row count.
- **Connection pool:** `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT` feed the
  production engine; a test runs 20 sessions and asserts `checkedout() == 0` (no leak)
  and `pool.size()` matches config.
- **Hot-read cache:** `inkstave.cache.RedisCache` (JSON, short TTL, fail-soft) caches
  **project metadata** post-authz, invalidated explicitly on rename/delete — conservative
  (correctness over hit rate). Disabled mode bypasses entirely.
- **CRDT throughput:** a smoke test applies a 500-update burst through pycrdt and asserts
  convergence within a small time bound (guards against an O(n²) regression).

## Consequences

- pytest-xdist added; `_configure_test_env`/`_no_real_network` updated;
  `inkstave.cache` + pool config + the gate/timing scripts + `just test-timed` added.
  10 new tests (gate self-tests, network guard, CRDT burst, cache hit/invalidate,
  cache-disabled, N+1 bound, pool leak). Eight env vars documented.
- Default suite stays green and **well under** the 2-minute gate, ~3× faster in parallel.
