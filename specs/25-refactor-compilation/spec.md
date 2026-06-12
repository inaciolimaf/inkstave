# Spec 25 — Refactor: Compilation (requirements)

## 1. Summary

A refactoring pass over the compilation subsystem built in specs 21–24
(Tectonic service, compile API + ARQ jobs, output storage, PDF preview UI). It
adds **no features**. Automated and manual analysis hunts for bugs, resource
leaks, temp-directory cleanup gaps, timeout/cancellation correctness issues,
security-model weaknesses, missing tests, and — given the project's hard
constraint — **test-speed regressions**, with special attention to ensuring **no
real LaTeX compile leaks into the unit or integration tiers**. Each finding is
evaluated (risk vs. value) and only worthwhile fixes are applied, keeping the
whole suite green and under the 2-minute budget.

## 2. Context & dependencies

- **Depends on:** specs **21, 22, 23, 24** (all implemented, all tests green).
- **Unlocks:** a healthier base for specs 26 (synctex) and 27 (log annotations),
  which build directly on the compile pipeline and stored artifacts.
- **Affected areas:** `backend/app/compile/**` (service, runner, workdir, jobs,
  outputs, api), the Alembic migrations for `compiles`/`compile_outputs`,
  `frontend/src/features/pdf-preview/**`, `infra/tectonic/packages.toml`, tests,
  CI test-tier configuration, docs.

## 3. Goals

- Find and fix correctness bugs and resource leaks in the compile pipeline.
- Guarantee **temp-dir cleanup** on every path (success, failure, timeout,
  cancel, exception, persistence-failure) with no orphaned workdirs.
- Verify **timeout and cancellation** behave correctly end-to-end (engine timeout
  < job timeout; cancel actually trips the `CancelToken`; no zombie processes).
- Close gaps in the **security model** documented in spec 21 (no-shell exec,
  rlimits, path-traversal defenses, output-size caps) and update the ADR if the
  model changed.
- Fill **missing tests** for edge cases discovered during the scan.
- **Protect the test budget:** add guards that make a real compile in a fast tier
  fail loudly, and re-measure suite time.

## 4. Non-goals (explicitly out of scope)

- New features, endpoints, UI, or config beyond what 21–24 already define.
- SyncTeX (spec 26) and structured log parsing/annotations (spec 27).
- Broad rewrites for taste alone; only changes with clear correctness, leak,
  security, or speed value.

## 5. Detailed requirements

This spec is procedural. Carry out the scan over the areas below, record findings,
apply the worthwhile fixes, and add tests. The output is a set of code changes
plus a changelog (§"Deliverables").

### 5.1 Scan checklist (what to look for)

**A. Temp-dir & file-handle leaks (spec 21 + the job in spec 22/23)**
- Is `cleanup_workdir` guaranteed via `finally` on *every* exit path, including
  exceptions in assembly, runner, output discovery, and persistence?
- With the spec-23 "job owns cleanup" approach (`keep_workdir=True` then job
  cleans up), is the workdir removed even when persistence raises?
- Are file handles / async readers (log read, artifact streaming) closed
  (context managers) so they don't leak FDs under load?
- Are orphaned workdirs from crashed workers ever reclaimed? Consider a
  startup/sweep that removes stale dirs older than a threshold under
  `COMPILE_WORKDIR_ROOT` (add only if worthwhile; it is a leak guard, not a
  feature).

**B. Timeout & cancellation correctness**
- Engine timeout (`TECTONIC_COMPILE_TIMEOUT_S`) must be strictly < job timeout
  (`COMPILE_JOB_TIMEOUT_S`); assert via settings validation. Fix if violated.
- Does the runner actually SIGTERM→SIGKILL and reap the child (no zombies)?
- Does cancel work when (i) job is still queued, (ii) job is mid-run; does the
  Redis cancel flag/pub-sub reliably trip the in-process `CancelToken`?
- Race: cancel arriving between status=running and the runner spawn — is it
  honoured?

**C. Concurrency / debounce (spec 22)**
- Are concurrency-cap and debounce checks free of TOCTOU races that could let two
  compiles for the same project run at once? (Check the enqueue path; consider a
  short Redis lock or a DB unique-ish guard.)
- Does the active-count query count exactly `queued`+`running`?

**D. Output storage (spec 23)**
- Range-request math correctness (off-by-one in `Content-Range`, 416 boundary,
  zero-length files, `bytes=-N` suffix ranges if claimed).
- ETag stability and 304 handling; `Content-Length` correctness for streamed
  responses.
- Retention job: does it delete **storage objects** as well as rows? Is it
  batch-bounded and idempotent? Does project-delete sweep storage?
- Authz on every output endpoint (no existence leak; 403/404 consistent with
  spec 08).

**E. Preview UI (spec 24)**
- Memory leaks: PDF.js documents/pages destroyed on unmount and on document
  replacement; `EventSource`/poll timers cleaned up on unmount and terminal
  state; no setState-after-unmount.
- Does client debounce prevent duplicate compiles; does cancel reset state; does
  the SSE→polling fallback always reach a terminal state?
- Accessibility regressions (aria-live status, labelled controls).

**F. Security model (spec 21)**
- Confirm no `shell=True` / string-interpolated commands anywhere.
- Confirm `safe_join` rejects absolute paths, `..`, and symlink escapes; add
  tests if thin.
- Confirm shell-escape is disabled in the Tectonic invocation and rlimits are
  applied; confirm the "trusted users" caveat is still accurately documented in
  the ADR. Update the ADR if the model drifted.

**G. Missing tests**
- Each fixed bug gets a regression test.
- Add edge-case tests revealed by the scan (empty project, missing main file,
  huge log truncation, unsatisfiable range, cancel-while-queued, etc.) if not
  already covered.

### 5.2 TEST-SPEED audit (highest priority)

This is the spec's signature concern. Do all of the following:

1. **Detect real compiles in fast tiers.** Grep/inspect the test suite for any
   path that could invoke the real `tectonic` binary or `LocalTectonicRunner`
   without stubbing (e.g. tests that construct `CompileService` with the real
   runner, or that don't inject a fake). Any such case in the unit/integration
   tier is a defect to fix.
2. **Add a hard guard.** Introduce a test-time safeguard so a real compile in a
   fast tier fails loudly rather than silently slowing the suite. Options
   (choose and document): a pytest autouse fixture/conftest hook that monkeypatches
   `LocalTectonicRunner.run` (or the subprocess spawn) to raise unless an opt-in
   marker (`smoke`/`RUN_REAL_COMPILE=1`) is set; and/or a CI step that asserts the
   fast tier spawns no `tectonic` subprocess.
3. **Confirm the smoke compile is isolated.** The single real smoke compile from
   spec 21 must be marker-gated and excluded from the default/fast run; verify it
   is and that CI's fast tier does not run it.
4. **Re-measure.** Record the full-suite wall time before and after this spec.
   It must remain **< 2 minutes**. If the scan revealed a slow test (even mocked
   — e.g. real `sleep`s in SSE/poll tests), tighten it (fake clocks, short
   intervals, assert-then-close).

### 5.3 Decision policy (apply only worthwhile fixes)

For each finding, classify and decide:
- **Apply now** if it is a real bug, leak, security gap, or speed regression with
  acceptable change risk.
- **Defer/skip** if low value, high risk, or properly belongs to a later spec
  (e.g. synctex/log-parsing) — record the rationale in the changelog.
- Never apply a "fix" that changes documented behaviour of 21–24 without noting
  it as an intentional, justified change.

### 5.4 Configuration

No new env vars unless a fix demands one (e.g. a stale-workdir-sweep threshold).
If added, document it in `.env.example` and the changelog and keep the default
conservative.

## 6. Overleaf reference (study only — never copy)

None. This is an internal refactor of Inkstave's own code.

## 7. Acceptance criteria

1. **Given** the compile pipeline, **when** any compile path runs to completion
   in any outcome (success/failure/timeout/cancel/exception/persistence-failure),
   **then** no workdir remains under `COMPILE_WORKDIR_ROOT` afterwards (asserted
   by a test for each path).
2. **Given** settings, **when** validated, **then**
   `TECTONIC_COMPILE_TIMEOUT_S < COMPILE_JOB_TIMEOUT_S` is enforced; a violating
   config fails fast with a clear error.
3. **Given** the full test suite is run with default options, **when** it
   executes, **then** **zero** real `tectonic` subprocesses are spawned (asserted
   by the speed-guard), and the only real compile is the opt-in smoke test which
   is skipped by default.
4. **Given** a real compile is (mistakenly) invoked in a fast-tier test, **when**
   that test runs, **then** the guard makes it fail loudly with an explanatory
   message rather than slowing the suite.
5. **Given** every bug fixed in this spec, **then** each has a regression test
   that fails on the pre-fix code and passes after.
6. **Given** the output range/ETag handling, **when** the audited edge cases run
   (zero-length, exact-boundary, unsatisfiable range, 304), **then** all behave
   per spec 23 (fix + test any that didn't).
7. **Given** the preview UI, **when** components unmount or replace the PDF
   document, **then** PDF.js resources and event/poll subscriptions are released
   (asserted by tests / no console warnings).
8. **Given** the whole suite, **when** measured, **then** it runs in < 2 minutes
   and the before/after timings are recorded in the changelog.
9. **Given** the security model, **when** reviewed, **then** the spec-21 ADR is
   accurate (no-shell, rlimits, path defenses, shell-escape disabled, trusted-
   users caveat); any drift is corrected.
10. **Given** the refactor is complete, **then** all pre-existing tests for specs
    21–24 still pass (no regressions).

## 8. Test plan

> Still no real compiles in fast tiers. Tests here are about proving the fixes
> and guarding speed.

- **Unit (pytest):** regression tests for each fixed bug; cleanup-on-every-path
  tests using a fake runner that raises at each stage; settings-validation test
  for the timeout invariant; range/ETag edge cases.
- **Unit (Vitest):** PDF.js/event-subscription cleanup on unmount and document
  replacement; no setState-after-unmount; debounce/cancel correctness.
- **Integration (pytest):** end-to-end job paths (stubbed service) asserting no
  orphaned workdirs and correct cancel/timeout status mapping; retention deletes
  storage + rows; project-delete sweeps storage.
- **Speed-guard test/CI step:** assert the fast tier spawns no `tectonic`
  process; verify the smoke test is marker-gated and excluded by default.
- **E2E (Playwright):** unchanged from spec 24 (mocked compile); only adjust if a
  leak/flake was found.
- **Performance/budget note:** record full-suite wall time before and after;
  replace any real `sleep` in SSE/poll tests with fake timers; keep < 2 min.

## 9. Deliverables / Definition of Done

- [ ] A **changelog** (e.g. `docs/refactors/25-compilation.md`) listing every
      finding, the decision (applied / deferred / skipped), and the rationale,
      plus before/after full-suite timings.
- [ ] All worthwhile fixes applied; behaviour of 21–24 preserved except where an
      intentional change is documented.
- [ ] Temp-dir cleanup guaranteed on all paths (criterion 1).
- [ ] Timeout/cancellation correctness verified (criteria 2, and cancel races).
- [ ] **No real compile in any fast tier**; speed-guard added; smoke test
      isolated (criteria 3–4).
- [ ] Regression tests for all fixed bugs (criterion 5).
- [ ] All acceptance criteria in §7 pass; all pre-existing tests still green.
- [ ] Full suite runs in < 2 minutes (timings recorded).
- [ ] Lint/format/type-check clean.
- [ ] Spec-21 security ADR reviewed/updated; any new env var documented.
- [ ] No Overleaf code copied.
