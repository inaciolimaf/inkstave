# Spec 71 — Fix-Pack: Backend & Tests 3 (validated issues)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a set of **confirmed issues** that two independent
reviewers validated against the codebase. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. They are **disjoint** from every other fix-pack (specs 68–90), so this
   pack can be applied in parallel by another agent without conflicts. **Do not
   touch any file outside the listed set.** If a fix seems to need a file that is
   not in scope, stop and report rather than reaching outside the set.
3. **Do not refactor unrelated code.** Make the smallest change that resolves
   each issue. Do not reformat untouched lines or restructure modules.
4. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest; Vitest + React
   Testing Library on the frontend). Match the existing style and test patterns.
5. **Test.** After applying the fixes, run the backend and frontend test suites.
   They must be **green** and the full suite must stay **under 2 minutes**. Add
   the new/updated tests described in §5 (Test plan). Use `just test-timed`
   (xdist) to confirm the budget.

This pack contains **one CRITICAL issue** (issue 150 — the history diff 413
handling makes the "too large to diff" fallback unreachable in production while
a mis-mocked test masks it). Treat that fix as the priority and verify it both
in code and in the updated test.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Close 9 validated history-diff, test-coverage, and docs gaps from specs
02/11/23/29/38/51 — including a critical broken "diff too large" fallback —
without changing public behaviour beyond the documented fixes.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
