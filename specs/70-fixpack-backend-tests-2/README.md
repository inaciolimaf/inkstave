# Spec 70 — Fix-Pack: Backend & Frontend Tests #2 (validated issues)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

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
3. **Do not refactor unrelated code.** Make the smallest change that resolves each
   issue.
4. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed (FastAPI +
   Pydantic v2 on the backend; Vite + React + TypeScript + Vitest/RTL on the
   frontend). Match the existing style and test patterns.
5. **Test.** After applying the fixes, run the backend (pytest) and frontend
   (Vitest) suites. They must be **green** and the full suite must stay **under
   2 minutes**. Add the new/updated tests described in §5.

When every issue is resolved, its acceptance criterion passes, and the suites are
green and under budget, this fix-pack is complete.

## One-line goal

Close 9 validated backend/frontend gaps from specs 02–57 (CORS/middleware notes,
a missing strict-mode startup-refusal test, two missing SyncTeX/PDF component
tests, an auth fail-open integration test, an agent type-contract fix, and two
layout/placement notes) without changing public behaviour beyond the documented
fixes.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not implement features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
