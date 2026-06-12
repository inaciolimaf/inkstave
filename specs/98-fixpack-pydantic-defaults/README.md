# Spec 98 — Fix-Pack: Pydantic mutable-default consistency

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a small set of **idiomatic-consistency fixes** for
Pydantic settings models. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. Do not touch any file outside the listed set. If a fix seems to need a
   file that is not in scope, stop and report rather than reaching outside it.
3. **Do not refactor unrelated code.** Make the smallest change that resolves
   each issue. Do not reformat untouched lines or restructure modules.
4. **Verify values byte-for-byte.** Before editing, read the **current** literal
   for each field in the real file. The lists/dict you wrap in a
   `default_factory` must reproduce the existing default **exactly** (same items,
   same order, same contents). Behaviour must not change.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns. Other modules already use
   `Field(default_factory=list)` correctly (e.g. `agent/context/models.py`) —
   mirror that style.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new/updated
   tests described in §8 (Test plan). Use `just test-timed` (xdist) to confirm
   the budget.

When every issue in `spec.md` is resolved, its acceptance criteria pass, and the
suite is green and under budget, this fix-pack is complete.

## One-line goal

Make Pydantic settings use explicit `Field(default_factory=...)` for mutable
(list/dict) field defaults instead of bare mutable literals — an
idiomatic-consistency hardening that changes **no** runtime behaviour.

## Note on Overleaf

There is **no Overleaf equivalent** for this fix-pack. It concerns Inkstave's own
Pydantic v2 settings models and idiomatic Python conventions; do not consult or
copy Overleaf source.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not change any default **value** — the wrapped defaults must equal the
  current ones byte-for-byte.
- Do not alter `Annotated[..., NoDecode]` typing, custom field decoders, or
  env-var parsing behaviour.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
