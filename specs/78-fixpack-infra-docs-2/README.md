# Spec 78 — Fix-pack: infra, docs & spec-deviation cleanup (batch 2)

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
3. **Follow conventions.** Match the existing code/doc/spec style (`CLAUDE.md`).
   Read neighbouring files before editing.
4. **Run the tests.** After fixing, run the affected backend (pytest) and
   frontend (Vitest) suites plus any docs-validation test. They must be **green**
   and the full suite must stay **under 2 minutes**.
5. **Verify.** Check every Acceptance criterion and Definition-of-Done item in
   `spec.md`.

This pack mixes small backend interface/spec alignments, two frontend
file-tree-node fixes, several documentation completeness fixes, a CI/CD smoke-test
gap, and one spec-text path correction.

## One-line goal

Align confirmed backend/spec/doc/infra deviations for specs 07, 17, 28, 35, 57,
and 58 with what the specs require.

## Do NOT (scope guard)

- Do not modify any file outside the set listed in `spec.md` §2.
- Do not change behaviour beyond what each fix specifies.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
