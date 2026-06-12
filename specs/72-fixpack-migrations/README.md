# Spec 72 — Fix-Pack: Migrations, Health & Tests (validated issues)

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
3. **Migrations rule (critical for this pack).** This pack touches the migrations
   area. **Never edit a released/applied migration.** The two history migrations
   in scope are referenced **only** for the documentation fix (issue 144) — that
   fix is a comment/attribution note, **not** a schema change. If any issue here
   genuinely required a schema change you would add a **new** Alembic migration;
   it does **not**, so no new migration is created in this pack. Do not alter the
   DDL of the existing migrations.
4. **Do not refactor unrelated code.** Make the smallest change that resolves
   each issue. Do not reformat untouched lines or restructure modules.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Alembic, Pydantic v2, ARQ, pytest; Vitest +
   React Testing Library on the frontend). Match existing style and test patterns.
6. **Test.** After applying the fixes, run the backend and frontend test suites.
   They must be **green** and the full suite must stay **under 2 minutes**. Add
   the new/updated tests described in §5 (Test plan). Use `just test-timed`
   (xdist) to confirm the budget.

This pack contains **one major issue** (issue 142 — the history compaction job
omits §5.4.2 step 2, the open-tail seal) and **one major-flagged frontend gap**
(issue 56 — file-tree keyboard model coverage). Make those fixes explicit and
fully covered by tests.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Close 9 validated migration-attribution, health-endpoint, history-compaction,
and frontend/backend test-coverage gaps from specs 02/16/17/22/34/36/59 —
adding the missing open-tail seal to the compaction job — without changing
released migrations.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not edit the DDL of any released migration (history migrations are in scope
  for a comment-only attribution note in issue 144).
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
