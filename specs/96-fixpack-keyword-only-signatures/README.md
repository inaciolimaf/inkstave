# Spec 96 — Fix-Pack: Keyword-Only Signatures & Intent-Revealing Methods

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a set of **confirmed readability/safety issues** at
specific call sites that two independent reviewers validated against the
codebase. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you
   may edit. **Do not touch any file outside the listed set.** If a fix seems to
   need a file that is not in scope, stop and report rather than reaching
   outside the set.
3. **Apply AFTER spec 94.** This pack edits `backend/src/inkstave/auth/refresh_store.py`
   and `backend/src/inkstave/collab/store.py`, which **spec 94 also touches**
   (clock injection). Spec 96 must be applied **after** spec 94 so the
   signature-only refactor here layers cleanly on top of 94's changes. If spec 94
   is not yet applied, stop and report.
4. **Smallest change, behaviour unchanged.** This is a **signature-only refactor**
   plus matching call-site updates (and, for one issue, splitting one
   control-couple flag into two clearly-named methods that share a private
   implementation). Runtime behaviour must be **identical**. Do not refactor
   unrelated code or reformat untouched lines.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Update any test
   that called an old signature; use `just test-timed` (xdist) to confirm the
   budget.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete. Move to spec 97.

## One-line goal

Make ambiguous call sites self-documenting by making boolean / multi-arg
parameters keyword-only, and split one control-couple flag into two clear methods
— with no change in behaviour.

> **No Overleaf equivalent.** These are Inkstave-internal call-site readability
> fixes; there is nothing in `../overleaf/` to study for this pack.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not change runtime behaviour — this is a signature/method-name refactor only.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
- Do not apply before spec 94 (shared files: `refresh_store.py`, `collab/store.py`).
