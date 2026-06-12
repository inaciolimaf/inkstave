# Spec 68 — Fix-Pack: Backend & Tests (validated issues)

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
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns.
5. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new/updated
   tests described in §5 (Test plan). Use `just test-timed` (xdist) to confirm
   the budget.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Close 22 validated backend, schema, config, and test-coverage gaps from specs
01–59 without changing public behaviour beyond the documented fixes.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
