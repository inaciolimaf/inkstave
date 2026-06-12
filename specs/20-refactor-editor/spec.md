# Spec 20 — Refactor: Editor & File-Tree UI (requirements)

## 1. Summary

A **refactoring** spec (every 5th). It adds no features. It is a structured
quality pass over everything built in Phase 2's frontend — the **project
dashboard (16)**, **file tree (17)**, **CodeMirror editor (18)** and **REST
autosave (19)**. The agent scans this code for bugs, accessibility issues,
re-render/performance problems, dead code and missing tests; evaluates each
finding by risk vs. value; applies the worthwhile fixes while keeping all tests
green; and records what was changed and what was deliberately skipped.

## 2. Context & dependencies

- **Depends on:** **16, 17, 18, 19** fully implemented with green tests. (It also
  touches the shared frontend foundation from **09** where the issue lives in
  code those Phase-2 specs rely on, e.g. the API client, toasts, query setup —
  but the focus is the Phase-2 UI.)
- **Unlocks:** a healthier base for Phase 3 (compilation UI) to build on.
- **Affected areas:** frontend (dashboard, file-tree, editor, autosave) and,
  where directly implicated, the shared frontend utilities. No new backend.

## 3. Goals

- Establish and preserve a **green baseline** (run the full suite first).
- Find and triage issues across these categories (see §5):
  bugs/correctness, accessibility, re-render/performance, dead code, missing
  tests, consistency/maintainability.
- Apply only **worthwhile** fixes (positive risk-adjusted value), each verified
  by tests, keeping behavior unchanged unless the change is a tested bug fix.
- Keep the suite green and under 2 minutes throughout.
- Produce a **changelog** of applied vs. skipped findings with rationale.

## 4. Non-goals (explicitly out of scope)

- New features or any scope from specs 21+.
- API/contract changes to specs 11–14 (the backend is not refactored here beyond
  what a frontend bug fix strictly requires; backend refactors belong to backend
  refactor specs).
- Cosmetic redesigns / visual restyling that change UX.
- Rewrites for their own sake. Prefer minimal, safe, test-backed edits.
- Upgrading major framework versions (risky, low value here) unless a finding
  proves it fixes a real bug and stays in budget.

## 5. Detailed requirements (the refactor process)

### 5.1 Establish baseline

1. Run the entire test suite (Vitest + Playwright) and record pass/fail + total
   runtime. **Do not proceed** with changes until green.
2. Capture current lint/format/type-check status (ESLint, Prettier, `tsc
   --noEmit`). Note any pre-existing warnings.
3. (Optional) Capture a bundle-size / dependency snapshot for the editor route.

### 5.2 Scan dimensions (what to look for)

Audit specs 16–19 code along these axes:

- **Correctness / bugs:**
  - Optimistic-update rollbacks that don't fully revert (dashboard create/rename/
    delete; file-tree create/rename/move/delete).
  - Autosave races: overlapping in-flight saves, lost edits during save, debounce
    not cancelled on unmount/doc-switch, `beforeunload` not flushing, stale
    closures capturing old `version`/`localText`.
  - Conflict (409) handling that can overwrite server data or strand the UI in
    `conflict`/`error`.
  - File-tree DnD edge cases: dropping a folder into its descendant, dropping on
    self, dropping outside any target.
  - CodeMirror lifecycle: view recreated on every render, listeners/compartments
    leaking, settings not reapplied on doc switch, focus lost after switching.
  - Query cache key mistakes (wrong invalidation, cross-project leakage).
  - Error/empty/loading states that can't be reached or get stuck.
- **Accessibility:**
  - File-tree ARIA `tree` correctness (roving tabindex, `aria-expanded/selected/
    level`, keyboard ops, type-ahead).
  - Dialog focus traps / focus restoration; destructive-action default focus.
  - `aria-live` for toasts and the save-status indicator.
  - Editor region labelling, read/edit state exposure, theme contrast (AA).
  - Visible focus rings; no color-only signals.
  - Run `axe` (jest-axe / @axe-core/playwright) on dashboard + workspace; fix
    serious/critical violations.
- **Re-render / performance:**
  - Unmemoized handlers/objects passed to large lists (file tree, project list)
    causing wasteful re-renders; add `React.memo`/`useCallback`/`useMemo` where
    it measurably helps (don't over-memoize).
  - Tree re-deriving the nested structure on every render; memoize derivations.
  - CodeMirror reconfigured/recreated unnecessarily; ensure compartment dispatch
    instead of view recreation.
  - Debounce/throttle correctness and timer cleanup.
- **Dead code / duplication:**
  - Unused components, props, exports, types; duplicated dialog/menu logic that
    should be a shared shadcn-based component; copy-pasted API error handling.
- **Missing tests:**
  - Untested branches found above (especially autosave conflict/offline, DnD
    guards, tree keyboard nav, optimistic rollback). Add focused tests.
- **Consistency / maintainability:**
  - Inconsistent error/toast handling, HTTP not confined to `api.ts`, snake_case
    leaking past the client boundary, ad-hoc CSS where a shadcn component exists.

### 5.3 Evaluate each finding (risk vs. value)

For every finding, record: description, location (file), category, **value**
(user/maintainer benefit), **risk** (chance of regression / scope creep), and a
**decision** (apply / skip / defer). Apply only net-positive, low-risk-or-
well-tested fixes. Prefer many small, independently-testable changes over one
large rewrite.

### 5.4 Apply fixes safely

- Make changes incrementally; run the suite after each meaningful change.
- For every **bug fix**, add a regression test that fails before and passes after.
- For accessibility fixes, add/extend `axe` assertions or RTL queries proving the
  corrected semantics.
- For performance fixes, prefer a test or a brief measurement note; never trade
  correctness for speed.
- Keep all edits within the approved stack and the no-Overleaf-copy rule.

### 5.5 Changelog & docs

- Write `docs/refactors/20-editor-file-tree.md` (or the established docs
  location) containing:
  - The baseline (suite status + runtime before).
  - A table of findings: category, location, decision, rationale.
  - Applied fixes (with linked tests) and deliberately **skipped** findings with
    why (e.g. "low value / high risk / out of scope / deferred to spec NN").
  - The after state (suite status + runtime; any bundle/perf deltas).

### 5.6 Configuration

- No new env vars. If a dev-only tool is added (e.g. `jest-axe`,
  `@axe-core/playwright`, `eslint-plugin-jsx-a11y`), it must be a permissive
  dev-dependency, must not slow the suite past budget, and is documented in the
  changelog.

## 6. Overleaf reference (study only — never copy)

> **None.** This is an inward-looking refactor of Inkstave's own Phase-2 code.
> There is no Overleaf equivalent to study, and no Overleaf code may be
> introduced while refactoring.

## 7. Acceptance criteria

1. **Given** the start of the spec, **then** the full suite is run and recorded
   green before any change (baseline captured).
2. **Given** the scan, **then** a findings list exists covering all six
   categories in §5.2, each with a risk/value evaluation and an apply/skip/defer
   decision (recorded in the changelog).
3. **Given** an applied **bug fix**, **then** a regression test exists that fails
   on the pre-fix code and passes after; user-visible behavior is unchanged
   except where the fix corrects a genuine bug.
4. **Given** an applied **accessibility fix**, **then** an `axe`/RTL assertion
   proves the corrected semantics; `axe` reports no serious/critical violations
   on the dashboard and the editor workspace after the pass.
5. **Given** an applied **performance fix**, **then** it is justified (test or
   measurement note) and does not change behavior.
6. **Given** all changes, **then** the full suite passes and runs in < 2 minutes;
   lint/format/type-check are clean (no new warnings introduced).
7. **Given** the spec is complete, **then** `docs/` contains the changelog of
   applied and skipped findings with rationale.
8. **Given** the whole pass, **then** no new feature or later-spec scope was
   added, no spec 11–14 API contract changed, and no Overleaf code was
   introduced.

## 8. Test plan

> The suite must remain green and under 2 minutes throughout.

- **Unit (Vitest + RTL):** add regression/behavior tests for each fixed bug and
  each closed coverage gap (autosave conflict/offline/coalescing, DnD guards,
  tree keyboard nav, optimistic rollbacks, CodeMirror lifecycle/compartments).
- **Accessibility:** `jest-axe` assertions on key components and/or
  `@axe-core/playwright` on the dashboard and workspace; assertions for ARIA
  tree semantics, dialog focus management, and `aria-live` regions.
- **Integration (Vitest + RTL + MSW):** keep existing spec 16–19 integration
  tests green; extend where a refactor touched data flow.
- **E2E (Playwright):** the existing Phase-2 flows (dashboard CRUD, tree ops,
  open doc, edit+autosave persist) must still pass unchanged; do not add new
  long flows.
- **Performance/budget note:** measure suite runtime before and after; if any
  added test risks the budget, scope it down or move detail to unit level. New
  dev tools (axe/eslint a11y) run only in the fast tiers.

## 9. Definition of Done

- [ ] Baseline captured (suite green + runtime) before changes.
- [ ] Findings list across all §5.2 categories with risk/value + decisions.
- [ ] Worthwhile fixes applied; each bug fix has a failing-before/passing-after
      test; behavior otherwise unchanged.
- [ ] All acceptance criteria in §7 pass.
- [ ] Full suite green and < 2 minutes; lint/format/type-check clean.
- [ ] Changelog of applied vs. skipped findings (with rationale) written in
      `docs/`.
- [ ] No new features / later-spec scope; no API contract changes; no Overleaf
      code introduced.
