# Spec 81 — Fix-pack: compile/logparse semantics & test gaps (batch 9)

**Type:** 🔧 fix-pack  ·  **Phase:** validation remediation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** for the Inkstave system. A validation pass
(two independent reviewers) confirmed the issues listed in [`spec.md`](spec.md).
Apply **exactly** those fixes — no more, no less.

Rules:

1. **Read the requirements.** The authoritative list of confirmed issues and the
   concrete fix for each is in [`spec.md`](spec.md). Apply each one as described.
2. **Files are disjoint from every other fix-pack (parallel-safe).** Only edit the
   files listed in `spec.md` §2 "Files in scope". Do **not** touch any file
   outside that set; other packs may be running concurrently.
3. **No unrelated refactors.** Fix the listed issues only.
4. **Keep tests green and fast.** Run the relevant suites after fixing; they must
   pass and the full suite must stay under the 2-minute budget.
5. **Follow `CLAUDE.md`.** Match existing style and the approved stack. Do not copy
   Overleaf code.

When every Acceptance criterion and Definition-of-Done item in `spec.md` passes,
this fix-pack is complete.

## One-line goal

Correct the compile log-excerpt slice direction, add the missing compile-job
defense-in-depth check, reconcile the logparse spec wording, and close several
confirmed backend/frontend test-coverage gaps — without regressions.

## Do NOT (scope guard)

- Do not edit files outside the "Files in scope" list in `spec.md` §2.
- Do not implement features from other specs or invent new scope.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
