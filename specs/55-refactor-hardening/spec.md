# Spec 55 — Refactor: hardening (requirements)

## 1. Summary

A refactoring pass over everything built in Phase 7's hardening work (specs
51–54): structured logging/metrics/tracing & health, the security middleware
(rate limiting, validation, CORS, secure headers, uploads, secrets, compile-
sandbox review, dependency audit), the performance & test-speed harness and the
2-minute CI budget gate, and the Playwright e2e suite. No new features. The goal
is to find and fix real defects — **security misses**, **observability gaps**,
**flaky e2e/integration tests**, and **slow tests breaching the budget** — to
remove smells and dead code, close test gaps, and record a changelog of what
changed and what was deliberately left, all while keeping the suite green and
under 2 minutes.

## 2. Context & dependencies

- **Depends on:** specs **51** (observability), **52** (security hardening), **53**
  (performance & test speed + the budget gate), **54** (e2e suite). Each must be
  implemented with passing tests before this pass.
- **Unlocks:** a trustworthy, fast, observable, secure base for Phase 7's
  remaining packaging/CI/docs specs (56–59) and the final release-readiness
  refactor (60).
- **Affected areas:** backend observability + security modules and their
  middleware ordering; the test harness/fixtures and CI budget gate; the e2e
  Playwright suite and its stubs/bring-up. Docs (changelog ADR; updates to the
  security checklist / field & metric reference where a fix changes them).

## 3. Goals

- Systematically **scan** the Phase-7 surface for: correctness bugs, **security
  misses** (missing/weak limits, header gaps, validation holes, leaky errors,
  un-redacted secrets, CORS slips, upload bypasses, sandbox config drift),
  **observability gaps** (missing/incorrect log fields, high-cardinality or
  mislabeled metrics, broken trace propagation, probes that lie), **flaky tests**
  (timing/order/parallelism-dependent), **slow tests** threatening the budget,
  resource leaks (gauges/contexts/connections not cleaned up), and smells/dead
  code/duplication.
- **Evaluate** each finding for risk vs. value; apply only worthwhile fixes.
- **Apply** the worthwhile fixes with accompanying tests that would have caught
  the bug.
- **Keep green:** the entire suite passes and stays **< 2 minutes** (measure
  before/after).
- **Document:** a changelog listing every change and every consciously-skipped
  finding with a one-line rationale (and target spec for deferrals).

## 4. Non-goals (explicitly out of scope)

- New features, new endpoints, new metrics/log fields, new env vars (unless
  removing one or fixing a real defect).
- Re-architecting observability, the security model, or the test strategy; only
  fix defects in what 51–54 produced.
- New product behaviour. Packaging/CI/docs work belongs to specs 56–59.
- Adding heavy/real externals (LLM/Tectonic/network) into the fast/default tiers.

## 5. Detailed requirements

### 5.1 Scan checklist (areas to inspect)

The pass MUST at least inspect these hot spots and assert they are correct (fix
if not):

**Spec 51 — observability**
- Request/trace IDs propagate end-to-end: HTTP → auth (user_id bound) → routers
  (project_id) → WS sessions → ARQ jobs (chained `request_id`). No context
  **leakage** across requests/tasks/workers (the contextvars reset in `finally`
  on every path, including exceptions and early returns).
- Log schema correctness: required fields always present; `http.path` is the
  **route template** (never a raw id-bearing URL — a cardinality/PII risk);
  redaction denylist actually catches every secret key (including those added in
  spec 52); no `null`-field spam.
- Metrics: no high-cardinality labels (no user/project ids, file paths, raw model
  strings, full URLs); gauges (`ws_connections_active`, `job_queue_depth`) return
  to baseline / fail soft; histograms use sensible buckets; the registry is
  double-registration-safe; `/metrics` and probes excluded from request metrics.
- Health/readiness honesty: `/readyz` truly fails (503) when a dependency is down
  and recovers; per-check timeouts prevent hangs; `/healthz` never touches deps.
- Tracing is a true no-op when `OTEL_ENABLED=false` (no imports/initialization,
  `trace_id == request_id`).

**Spec 52 — security**
- **Security misses (highest priority):** every sensitive endpoint actually
  carries its rate-limit policy (grep auth/compile/agent/upload routes for the
  dependency); secure headers appear on **all** responses including 404/error;
  CORS never emits `*`+credentials and the prod empty-allow-list boot guard fires;
  the JWT-secret strength boot guard fires in `production`.
- Validation holes: `extra="forbid"` is on every request model; string/list/body
  size caps are present and enforced (including streamed bodies); typed path
  params reject malformed ids (422 not 500).
- Upload bypasses: size cap aborts mid-stream (not after buffering); content-sniff
  rejects type spoofing; filename sanitization blocks traversal/NUL/absolute
  paths and overlong names; SVG/EPS risk noted.
- Error hygiene: no stack traces / internal messages leak to clients; consistent
  404-vs-403 (no existence enumeration); 429 carries `Retry-After`.
- Secrets: never logged (verify against real log output, not just the denylist);
  rotation doc present; compile environment carries no inherited secrets.
- Compile-sandbox config drift: shell-escape/`\write18` still disabled, timeout +
  output/size limits still set, temp dir cleaned; the trusted-users caveat doc
  still present.
- Rate-limiter fail-open behaviour is intentional and tested (Redis down ⇒ allow +
  warn + error counter), and the limiter's Redis op is atomic (no race).

**Spec 53 — performance & test speed**
- Parallel DB strategy is robust: template migrated once, per-worker DBs isolated,
  per-test rollback works under xdist with no cross-worker bleed; no pool
  deadlocks/leaks.
- External guards actually trip: real Tectonic/LLM/non-local network in the fast
  tier fails the test (verify the guard isn't accidentally bypassed).
- N+1 assertions still hold on the list endpoints; added indexes still serve their
  queries; cache invalidation is correct (no stale reads after writes) and authz-
  safe.
- The **budget gate** measures wall-clock correctly and fails over 120 s / warns
  over 90 s; `test-timing.json` is produced; the slow-test detector flags
  >`SLOW_TEST_FAIL_S` non-`@slow` tests; `@slow` truly excluded by default.
- **Slow-test hunt:** identify the current slowest tests; speed up or quarantine
  any non-`@slow` test that risks the budget. Record before/after timings.

**Spec 54 — e2e**
- **Flaky-test hunt (highest priority for e2e):** find and fix nondeterminism —
  fixed `waitForTimeout` for readiness, racing on un-awaited network/selectors,
  shared-state collisions across parallel workers, storage-state reuse bugs,
  order-dependence. Replace timeouts with proper waits; isolate per-worker data.
- Determinism: the LLM stub and compile mock are truly deterministic; nothing is
  applied by the agent before the user clicks apply; the two-context collab spec
  reliably observes live propagation.
- Bring-up reliability: stack starts reproducibly from a clean checkout;
  migrations applied; clean DB per run; traces/videos only on failure.
- Smoke vs full split honoured: `@full` excluded from the default budget; smoke
  stays within its e2e sub-budget.

**Cross-cutting**
- Middleware ordering (context → headers → body-size → CORS → routing → rate-limit
  → auth → handler) is correct and tested (headers/ids present even on rejected
  requests).
- Consistent typed errors and status codes across the hardening surface.
- No dead code, commented-out blocks, unused exports, or now-unused env vars left
  by Phase 7.
- Duplicated logic consolidated (e.g. one redaction list shared by logger and the
  secret-name set; one rate-limit key derivation).

### 5.2 Process requirements

- Produce a written **evaluation** for each non-trivial finding: severity,
  likelihood, blast radius, and a keep/fix/defer decision. Defer items that are
  real but better handled by a named later spec (e.g. prod Docker hardening → 56,
  CI pipeline specifics → 57, docs → 58), citing it.
- For every applied fix, add or update a test that fails before and passes after
  (where feasible). **Security and flakiness fixes MUST get a test** (for
  flakiness, a deterministic regression or a stress/repeat assertion that would
  have caught the race).
- Keep changes minimal and behaviour-preserving for legitimate flows; do not
  refactor for taste in ways that risk regressions or the budget.
- **De-flake methodology:** for suspected flaky tests, run them repeatedly (e.g.
  `--count`/`--repeat-each` locally, outside the default suite) to reproduce, fix
  the root cause (not by adding sleeps or blanket retries), and record it.

### 5.3 Changelog

- A `docs/refactors/55-hardening.md` (or the established refactor-log location)
  listing: each change (what, why, files), each finding deliberately
  **skipped/deferred** (with rationale + target spec), the before/after of any
  acceptance-criterion correction, the **before/after suite runtime**, and the
  **list of de-flaked or quarantined tests**. Reference it from `docs/`. Update
  the security checklist (spec 52) and the log/metric reference (spec 51) if a fix
  changes them.

### 5.4–5.5 (data model / config)

- No intentional data-model changes. If a fix needs an index/constraint to close a
  real bug (e.g. a missing composite index found during the N+1 re-audit), ship a
  forward-only Alembic migration and note it in the changelog.
- No new env vars; remove any now-unused ones found during the scan (documenting
  the removal in `.env.example` and the changelog).

## 6. Overleaf reference (study only — never copy)

None. This is an internal refactor driven by Inkstave's own code and the
acceptance criteria of specs 51–54. The no-copy rule still applies.

## 7. Acceptance criteria

1. A documented scan of the spec 51–54 surface exists, covering at least the §5.1
   checklist, each item marked verified-correct or fixed.
2. Every applied fix is accompanied by a test that exercises the fixed behaviour;
   all **security** fixes and all **flakiness** fixes have a regression test.
3. **No security misses remain** from the §5.1 list: an automated test or
   documented audit shows every sensitive route is rate-limited, secure headers
   appear on all responses (incl. errors), CORS/secret/boot guards fire, uploads
   can't be bypassed, and no secret is logged.
4. **No observability gaps remain:** trace/request IDs propagate end-to-end with
   no context leakage; the log schema and metric labels are correct and
   low-cardinality; `/readyz` fails and recovers truthfully.
5. **Flaky e2e/integration tests are eliminated or fixed:** the de-flaked tests are
   listed in the changelog; the suite is reproducibly green across repeated runs
   (no reliance on blanket retries to mask races).
6. **The suite is within budget:** full suite passes and runs in **< 2 minutes**;
   the spec-53 budget gate is green; before/after runtimes are recorded, and any
   slow test that breached the budget was sped up or justified as `@slow`.
7. A changelog records every applied change and every deliberately-skipped finding
   with rationale (and target spec for deferrals), plus before/after runtime and
   the de-flaked-test list.
8. No new features were added; no behavioural regression for legitimate flows
   (prior specs' acceptance criteria still pass).

## 8. Test plan

> Keep the full suite under 2 minutes — this pass *defends* the budget. Reuse the
> existing harnesses (in-process metrics registry, fakeredis limiter tests, the
> Playwright stubs); avoid adding heavy e2e unless a fix specifically needs one.

- **Unit / integration additions (pytest):**
  - Regression tests for each applied backend fix: context-leakage on the
    exception path; redaction of any newly-found secret key; a missing rate-limit
    guard now present (guard-coverage enumeration over sensitive routes);
    header-on-error responses; validation/upload bypass closed; readiness
    fail/recover; gauge-returns-to-baseline on WS/job crash.
  - An automated guard-coverage check (sensitive routes ⇒ a rate-limit policy
    present), analogous to the spec-34 authz coverage check.
  - Slow-test/budget-gate self-checks still pass after changes.
- **Unit / integration additions (Vitest):** regression tests for any frontend
  fix found (none expected unless a hardening change touched the SPA).
- **E2E (Playwright):** de-flaked specs run reliably; if a flaky race is fixed,
  add a deterministic assertion (proper wait) that would have failed before. No
  new heavy/real-external e2e in the default tier.
- **Performance/budget note:** measure suite runtime before and after; record in
  the changelog. If any added test threatens the budget, move slow assertions to
  in-process harnesses, optimize, or mark `@slow`. The whole point is the suite
  stays fast and green.

## 9. Definition of Done

- [ ] §5.1 scan completed and documented; each item verified or fixed.
- [ ] All worthwhile fixes applied with accompanying tests; security and
      flakiness fixes have regression tests (AC 2–5).
- [ ] No security misses and no observability gaps remain (AC 3–4).
- [ ] Flaky tests eliminated/fixed and listed; suite reproducibly green (AC 5).
- [ ] Full suite green and **< 2 minutes**; the spec-53 budget gate green;
      before/after runtimes recorded (AC 6).
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`,
      ESLint).
- [ ] Changelog written listing applied changes, skipped/deferred findings with
      rationale, runtime delta and de-flaked tests (AC 7); any forward-only
      migration noted; security checklist / metric-log reference updated if
      changed.
- [ ] No new features; no regression to specs 51–54 acceptance criteria (AC 8).
- [ ] No Overleaf code copied.
