# Spec 79 — Fix-pack: backend/e2e test-coverage gaps + collab/ws nit (batch 7)

**Type:** 🔧 fix-pack  ·  **Phase:** validation remediation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** spec of the Inkstave system. A validation
pass (two independent reviewers) confirmed the issues bundled here. Each issue is
**real** and **reproducible**. Apply exactly the fixes described in
[`spec.md`](spec.md) — no more, no less.

Do this:

1. **Read the requirements.** The authoritative, per-issue fix list is in
   [`spec.md`](spec.md). Apply *each* listed fix concretely.
2. **Stay in scope.** This fix-pack's files are **disjoint** from every other
   fix-pack, so it is parallel-safe. **Do NOT touch any file outside the listed
   set** (see spec.md §2). No unrelated refactors.
3. **Follow conventions.** Match the existing code/test style (`CLAUDE.md`). Read
   neighbouring code (existing Playwright specs, unit tests) before adding new code.
4. **Run the tests.** After fixing, run the affected backend (pytest), frontend
   (Vitest), and Playwright e2e suites. They must be **green** and the full suite
   must stay **under 2 minutes** (slow work stubbed; e2e kept minimal).
5. **Verify.** Check every Acceptance criterion and Definition-of-Done item in
   `spec.md`.

This pack is mostly **missing-test-coverage** remediation (two missing Playwright
e2e specs, several unit/integration assertions) plus one small collab/ws
bandwidth/spec-deviation fix and one frontend agent-panel adjustment.

## One-line goal

Close the confirmed e2e/unit/integration coverage gaps and the collab/ws + agent
panel deviations for specs 08, 13, 17, 27, 29, 32, and 46.

## Do NOT (scope guard)

- Do not modify any file outside the set listed in `spec.md` §2.
- Keep new e2e tests minimal and within the suite budget.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
