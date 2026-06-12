# Spec 95 — Fix-Pack: TreeEntity-fetch DRY-up & dead re-export (validated issues)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a small set of **confirmed issues** found while
reviewing the file-tree services. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit (plus any small new helper module the spec allows). **Do not touch any
   file outside that set.** If a fix seems to need a file that is not in scope,
   stop and report rather than reaching outside the set.
3. **Do not refactor unrelated code.** Make the smallest change that resolves
   each issue. Do not reformat untouched lines or restructure modules. This is a
   **behaviour-preserving** refactor: the same exception types and messages must
   be raised at every call site as before.
4. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns. Read the neighbouring code before editing.
5. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new unit
   test described in §5 (Test plan). Use `just test-timed` (xdist) to confirm
   the budget.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Remove the duplicated TreeEntity-fetch logic by extracting one shared helper,
and delete a dead re-export — with no change in observable behaviour.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not change any exception type, message, or status code raised at a call site.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code (there is **no Overleaf equivalent** for this
  internal refactor — it is pure Inkstave hygiene).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
