# Spec 60 — Final Refactor & Release-Readiness Pass (requirements)

## 1. Summary

This is the **final** spec: a system-wide refactoring and release-readiness pass
over everything built in specs 01–59. It adds **no features**. It scans every
area for remaining bugs, smells, security issues, documentation gaps, and
flaky/slow tests; verifies the full suite is **green and under 2 minutes**; runs
an explicit **originality / license audit** confirming Inkstave shares no code
with Overleaf; and produces a **release checklist** and a **final changelog** of
refactors applied vs. deliberately skipped (with rationale).

## 2. Context & dependencies

- **Depends on:** **ALL** prior specs (01–59), implemented with passing tests.
- **Unlocks:** a tagged, release-ready Inkstave.
- **Affected areas:** potentially any (backend, frontend, collab, infra, docs,
  tests) — but only via low-risk, high-value fixes; primarily `docs/`
  (changelog, release checklist, audit report) and small targeted patches.

## 3. Goals

- A structured scan of the whole codebase for: correctness bugs, code smells/dead
  code, security issues, doc gaps, and flaky/slow tests.
- A risk-vs-value decision for each finding; **apply** the worthwhile, low-risk
  ones; **record** the rest as deliberately skipped with rationale.
- Verified **green suite under 2 minutes**, with no flaky tests.
- An explicit **originality / license audit** proving independence from Overleaf.
- A **release checklist** (build, deploy, migrate, bootstrap, smoke) and a **final
  changelog** committed under `docs/`.

## 4. Non-goals (explicitly out of scope)

- New features, new endpoints, new UI, new dependencies.
- Large architectural rewrites or risky refactors (defer/record instead).
- Performance work beyond keeping the suite within budget and removing obvious
  waste (deep perf is spec 53's remit).

## 5. Detailed requirements

### 5.1 System-wide scan (areas & method)

Systematically review every area built so far. For each, enumerate findings with
severity and a proposed action. Areas:

1. **Backend** — error handling, async correctness (no blocking calls in async
   paths), N+1 queries, transaction boundaries, input validation, dead code,
   inconsistent patterns vs. early-spec conventions.
2. **Auth & access control** — token handling, session/refresh revocation, authz
   enforcement across REST + WS + compile (spec 34), missing guards.
3. **Collaboration / CRDT** — WS auth, room isolation, persistence correctness,
   resource cleanup, backpressure.
4. **Compilation** — sandbox isolation, timeouts/limits, temp-dir cleanup, log
   handling.
5. **AI agent** — never-auto-apply invariant, tool sandboxing, rate/cost limits
   (spec 49), prompt-injection surface, secret handling.
6. **Frontend** — error/loading/empty states, accessibility, console errors,
   bundle obviously-bloated imports, strict-mode/type issues.
7. **Infra** — Dockerfiles (non-root, no secrets baked, image size), compose
   healthchecks, nginx (`/metrics` blocked, upgrade headers), CI budget gate.
8. **Tests** — flakiness (timing/order dependence), slowness, gaps in critical
   paths; confirm slow work stays in async jobs and is mocked in the fast tiers.
9. **Docs** — accuracy vs. current behavior, broken links, stale env vars,
   OpenAPI sync (spec 58).

For each finding record: id, area, description, severity (low/med/high),
risk-of-fix, value-of-fix, decision (apply/skip), and (if applied) the change
reference; (if skipped) the rationale.

### 5.2 Security pass

- Re-verify spec-52 hardening still holds: rate limiting, input validation, CORS,
  security headers, secret handling (no secrets in images/logs/repo).
- Dependency check: run the backend (`uv`/`pip-audit`-style) and frontend
  (`pnpm audit`) advisories; triage and patch high-severity, fixable issues that
  don't break the budget; record the rest.
- Confirm `.env`/secrets are not committed and `.dockerignore`/`.gitignore` cover
  them.

### 5.3 Test-suite health & budget

- Run the full suite repeatedly (e.g. several times and/or with randomized order)
  to detect flakiness; fix or quarantine-and-document any flaky test.
- Measure total runtime; confirm **< 120 s** for unit + integration + e2e.
  If over, reduce by mocking/parallelizing (no feature loss). Record the measured
  number.
- Confirm no test performs real LaTeX compiles, real LLM calls, or real network
  in the fast tiers.

### 5.4 Originality / license audit (mandatory)

Produce `docs/originality-audit.md` confirming Inkstave shares **no code** with
Overleaf:
- **Method:** describe the checks performed — e.g. confirm Inkstave's stack
  (Python/FastAPI/SQLAlchemy/pycrdt/Tectonic) differs from Overleaf's
  (Node/Express/Mongo/sharejs); spot-check that files referencing Overleaf paths
  contain only **independent** implementations; search the Inkstave tree for
  copied identifiers/comments/strings that would indicate copied Overleaf code
  (e.g. Overleaf-specific module names, AGPL headers, distinctive Overleaf
  internal strings) and confirm **none** are present; verify `LICENSE` is MIT and
  no AGPL headers exist in Inkstave source.
- **Result:** a clear statement that the audit passed (or a list of remediations
  applied if anything was found), plus the commands/queries used so the audit is
  reproducible.
- Confirm every spec's "Overleaf reference" sections are *study-only* and no
  reference material was vendored into the repo.

### 5.5 Release checklist & changelog

- `docs/release-checklist.md` — an actionable, ordered checklist to cut a
  release: tests green & < 2 min, lint/type-check clean, images build within size
  targets (spec 56), compose up healthy, migrations run (spec 57), admin
  bootstrap works on a fresh DB, env validation fails fast on missing secrets,
  docs/OpenAPI in sync (spec 58), originality audit passed, version tag, and a
  smoke test of the key user flow.
- `docs/CHANGELOG.md` (or extend an existing one) — a final entry for this pass:
  the list of refactors **applied** (with one-line each) and refactors
  **deliberately skipped** (with rationale), plus a high-level summary of the
  release-ready state. Keep it factual and concise.

### 5.6 Configuration

- No new runtime config. Any audit/scan tooling is invoked from CI (spec 57) or
  documented in `CONTRIBUTING.md`; record commands in the changelog/checklist.

## 6. Overleaf reference (study only — never copy)

**None.** This is a process spec with no Overleaf reference. The only
Overleaf-related activity is the **originality audit** in §5.4, which exists to
confirm the absence of Overleaf code — not to study it.

## 7. Acceptance criteria

1. **Given** the whole codebase, **when** the scan in §5.1 completes, **then** a
   findings list exists with severity, risk/value, and an apply/skip decision for
   each item, captured in the changelog/audit docs.
2. **Given** the apply decisions, **when** the worthwhile low-risk fixes are
   applied, **then** the full test suite remains green and no new feature scope was
   introduced.
3. **Given** the security pass (§5.2), **when** dependency advisories are
   reviewed, **then** high-severity fixable issues are patched (or explicitly
   recorded as skipped with rationale), and no secrets exist in the repo/images/
   logs.
4. **Given** the suite run repeatedly/with randomized order, **when** measured,
   **then** it is **non-flaky** and completes in **< 2 minutes**, with the measured
   time recorded.
5. **Given** the originality audit (§5.4), **when** it runs, **then**
   `docs/originality-audit.md` exists, documents the reproducible checks, and
   concludes that **no Overleaf code** is present (MIT `LICENSE`, no AGPL headers,
   no copied Overleaf identifiers/strings).
6. **Given** `docs/release-checklist.md`, **when** followed on a clean checkout,
   **then** every item is actionable and the system reaches a healthy, usable
   running state (build → compose up → migrate → bootstrap → smoke).
7. **Given** `docs/CHANGELOG.md`, **when** read, **then** it lists the applied and
   deliberately-skipped refactors (with rationale) for this pass.
8. **Given** the docs, **when** the spec-58 doc tests run, **then** links and
   OpenAPI remain in sync (no regressions introduced by this pass).

## 8. Test plan

> This pass must keep the suite green and within budget; it primarily *verifies*
> and lightly fixes rather than adding test surface.

- **Regression:** the entire existing suite (unit + integration + e2e) must pass
  unchanged in intent; any fix applied must keep or improve coverage. Add
  targeted regression tests only for bugs actually fixed in this pass.
- **Flakiness check:** run the suite multiple times and/or with `--randomly`/
  randomized order; assert stable green across runs.
- **Budget check:** record total wall-clock of the test tiers; assert < 120 s
  (the spec-57 CI gate enforces this automatically).
- **Originality audit checks:** the documented searches/queries in §5.4 run and
  return clean (no AGPL headers, no copied Overleaf strings); these may be wired
  as a small CI/grep check that the audit references.
- **Docs checks:** spec-58 link + OpenAPI-sync tests still pass after any changes.
- **Performance/budget note:** no new slow tests; audit/scan tooling runs outside
  the fast suite (CI or local), not inside the 2-minute budget.

## 9. Definition of Done

- [ ] System-wide scan completed; findings recorded with apply/skip decisions.
- [ ] All worthwhile, low-risk fixes applied; no new feature scope added.
- [ ] Full suite green, non-flaky, and < 2 minutes (measured time recorded).
- [ ] Security/dependency pass done; high-severity fixable issues patched or
      recorded; no secrets in repo/images/logs.
- [ ] `docs/originality-audit.md` produced and passing (no Overleaf code; MIT
      license; reproducible checks).
- [ ] `docs/release-checklist.md` produced and verified actionable.
- [ ] `docs/CHANGELOG.md` final entry lists applied vs. skipped refactors.
- [ ] Lint/format/type-check clean across the project.
- [ ] No Overleaf code anywhere (confirmed by the audit).
