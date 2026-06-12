# Spec 77 — Fix-pack: backend & frontend test-coverage gaps (batch 6)

**Type:** 🔧 fix-pack  ·  **Phase:** validation remediation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** spec of the Inkstave system. A validation
pass (two independent reviewers) confirmed the issues bundled here. Each issue is
**real** and **reproducible**. Your job is to apply exactly the fixes described in
[`spec.md`](spec.md) — no more, no less.

Do this:

1. **Read the requirements.** The authoritative, per-issue fix list is in
   [`spec.md`](spec.md). Apply *each* listed fix concretely.
2. **Stay in scope.** This fix-pack's files are **disjoint** from every other
   fix-pack, so it is parallel-safe. **Do NOT touch any file outside the listed
   set** (see spec.md §2). No unrelated refactors, no drive-by cleanups.
3. **Follow conventions.** Match the existing code/test style (`CLAUDE.md`). Read
   neighbouring code before adding new code.
4. **Run the tests.** After fixing, run the affected backend (pytest) and
   frontend (Vitest) suites. They must be **green** and the full suite must stay
   **under 2 minutes**.
5. **Verify.** Check every Acceptance criterion and Definition-of-Done item in
   `spec.md`.

This pack is mostly **missing-test-coverage** remediation: add the
acceptance-criterion-mandated assertions/tests that the original specs required
but that were never written. Make each test concrete and assert real values.

## One-line goal

Close the confirmed test-coverage gaps for specs 07, 18, 37, 42, and 48 so each
spec's acceptance criteria and test plan are actually exercised.

## Do NOT (scope guard)

- Do not modify any file outside the set listed in `spec.md` §2.
- Do not change production/source behaviour — these are test-only fixes (the code
  under test is already correct per the reviewers).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
