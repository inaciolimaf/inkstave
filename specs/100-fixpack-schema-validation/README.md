# Spec 100 — Fix-Pack: Request-Schema Validation (fail-fast 422)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it tightens two request schemas so invalid input is rejected at
the Pydantic boundary (a clean **422**) instead of deeper in the service layer.
Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Inspect before you edit.** Before writing either fix, read the real source:
   the current schemas in `schemas/tree.py`, the `MAX_TREE_ENTITY_NAME_LENGTH`
   constant and `validate_name_segment` in `services/safe_path.py`, and the
   actual diff-status values in `agent/diffs/models.py` (`ProposedDiffStatus`).
   The constraints you add must match those exactly — do not guess the values.
3. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. Make the **smallest** change that resolves each issue. Do not reformat
   untouched lines, restructure modules, or refactor unrelated code. If a fix
   seems to need a file outside the set, stop and report.
4. **Preserve all valid-input behaviour.** Do **not** remove the service-layer
   `validate_name_segment` call — the schema constraint is an *additional*
   fail-fast guard, not a replacement (the service also rejects illegal
   characters, path separators and reserved names). Valid status filters must
   return exactly the same results as before.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the
   new/updated tests described in §8 (Test plan). Use `just test-timed` (xdist)
   to confirm the budget.

When every issue in `spec.md` is resolved, its acceptance criteria pass, and the
suite is green and under budget, this fix-pack is complete.

## One-line goal

Tighten two request schemas so invalid input is rejected at the Pydantic
boundary (fail-fast 422) instead of deeper in the service layer.

## No Overleaf equivalent

These are Inkstave-internal request-schema hardening fixes. There is **no
Overleaf equivalent** to study — implement strictly from `spec.md`.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not remove the service-layer `validate_name_segment` call.
- Do not change behaviour for valid inputs (names or status filters).
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
