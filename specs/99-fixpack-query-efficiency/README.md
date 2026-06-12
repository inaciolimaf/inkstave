# Spec 99 — Fix-Pack: Query Efficiency & Bounded Tree Fetches

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a small set of **confirmed performance issues** found by
review against the codebase. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Inspect the real code first.** Open each file in §2 of `spec.md` and confirm
   the line references still match before editing. Make the **smallest change**
   that resolves each issue; do not reformat untouched lines or restructure
   modules.
3. **Apply ORDER constraint.** This pack edits
   `backend/src/inkstave/services/tree_service.py`, which **spec 95 also
   refactors**. Spec 99 **must be applied AFTER spec 95** so it lands on the
   refactored `tree_service.py`. If spec 95 is not yet applied, **stop and
   report** rather than editing an about-to-be-rewritten file.
4. **Preserve behaviour for normal-size projects.** Every current
   response/return shape (`FileRead`, `TreeRead`, compile inputs) must be byte-for-byte
   identical for normal projects. Any new limit must have a **generous default**
   so existing tests and real projects are unaffected.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2 settings, pytest). Match the
   existing style, the `config_groups.py` settings pattern, and the
   `tree_errors.py` domain-error pattern.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new/updated
   tests described in §8. Use `just test-timed` (xdist) to confirm the budget.

When every issue in `spec.md` is resolved, its acceptance criteria pass, and the
suite is green and under budget, this fix-pack is complete.

## One-line goal

Remove an N+1 query in file reads and bound unbounded full-tree fetches so large
projects don't blow up — without changing behaviour for normal-size projects.

## No Overleaf equivalent

There is **nothing to study in `../overleaf/`** for this pack: these are
Inkstave-internal query-shape and safety-cap fixes specific to Inkstave's
SQLAlchemy models and settings. Do **not** look for or copy an Overleaf approach.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not apply this pack before spec 95 (see ORDER constraint above).
- Do not change `FileRead`, `TreeRead`, or compile-input shapes for normal projects.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
