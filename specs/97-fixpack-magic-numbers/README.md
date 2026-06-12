# Spec 97 — Fix-Pack: Magic Numbers in Agent Budget & Section-Locate

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it replaces a small set of **business-meaning magic numbers** with
named, documented constants. The behaviour must not change. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. They are **disjoint** from every other fix-pack, so this pack can be
   applied in parallel by another agent without conflicts. **Do not touch any file
   outside the listed set.** If a fix seems to need a file that is not in scope,
   stop and report rather than reaching outside the set.
3. **Smallest change, behaviour unchanged.** Replace each literal with a named
   constant whose value is **numerically identical**. Do not retune scores, do not
   change the budget windows, do not reformat untouched lines or restructure
   modules. The named constant must evaluate to the exact value it replaces.
4. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns.
5. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. The existing agent
   budget and section-locate tests must pass unchanged; add only the small guard
   tests described in §5 (Test plan). Use `just test-timed` (xdist) to confirm the
   budget.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Replace the business-meaning magic numbers in the agent budget and section-locate
code with named, documented constants (and surface the budget TTL via settings
where natural), eliminating the duplicated `172800` literal — with **no** change
in behaviour.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not change any numeric value: every constant must equal the literal it
  replaces.
- Do not retune the locate scores or the budget windows; ranking and budget
  decisions must be byte-for-byte identical.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code (there is **no Overleaf equivalent** for either
  the agent budget or the section-locate code — both are Inkstave-only).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
