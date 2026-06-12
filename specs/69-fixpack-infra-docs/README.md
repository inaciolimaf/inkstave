# Spec 69 — Fix-Pack: Infra & Docs (test-budget gate) (validated issues)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / infra  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a set of **confirmed issues** that two independent
reviewers validated against the codebase. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md). Apply *every* issue listed there — no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. They are **disjoint** from every other fix-pack, so this pack can be
   applied in parallel without conflicts. **Do not touch any file outside the
   listed set.** If a fix seems to need an out-of-scope file, stop and report.
3. **This pack is the budget-gate pack.** Its two **CRITICAL** issues are that CI
   runs pytest **without `-n auto`**, so the 2-minute budget gate measures
   ~3-minute single-threaded wall-clock and would fail the build. Fixing these is
   the headline of this pack — get them exactly right (see §3.1).
4. **Do not refactor unrelated code.** Make the smallest change that resolves each
   issue.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed.
6. **Test.** After applying the fixes, run the suite via `just test-timed` (the
   xdist budget path) and confirm it is **green** and **under 2 minutes**. The
   whole point of this pack is that the default/CI path now measures parallel
   wall-clock.

When every issue is resolved, the CI/default commands pass `-n auto`, and the
budget gate measures parallel wall-clock under 2 minutes, this fix-pack is done.

## One-line goal

Make the documented default and CI test commands match the budgeted xdist path so
the 2-minute gate passes, and bring the testing ADR/docs and the slow-test
detector in line with reality.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md` (in particular, do not edit
  application/source code or backend test files — those belong to other packs).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not weaken the budget gate to "pass" — make the measured run genuinely fast.
