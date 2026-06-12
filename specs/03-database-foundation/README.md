# Spec 03 — Database Foundation

**Type:** 🟢 feature  ·  **Phase:** Phase 0 — Foundations  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **01** (compose Postgres,
   `DATABASE_URL`) and **02** (app factory, lifespan, settings, DI conventions).
   Both must be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. Note Overleaf's `web` service uses **MongoDB/Mongoose** while
   Inkstave uses **Postgres/SQLAlchemy**; the `history-v1` service uses Postgres
   + Knex migrations and is the closest reference for migration discipline.
   **Do not copy or translate any Overleaf code** — AGPLv3 vs MIT.
4. **Implement** the async SQLAlchemy 2.x engine/session, declarative `Base`
   with mixins (UUID id, timestamps), constraint naming conventions, the FastAPI
   session dependency with proper transaction handling, Alembic configured for
   async + autogenerate, and one trivial example table proving the migration
   workflow — all as described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan. The DB layer is tested
   against an **ephemeral/transactional** Postgres; tests stay fast.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` for the migration workflow and
   naming-convention choices.

When all Definition-of-Done items pass, this spec is complete. Move to spec 04.

## One-line goal

After this spec Inkstave has Postgres wired in via async SQLAlchemy 2.x and
Alembic, with a base model + mixins, constraint naming conventions, a
transaction-scoped FastAPI session dependency, an async autogenerate migration
workflow, and a proven example migration.

## Do NOT (scope guard)

- Do not add domain models (users, projects, files, etc.) — those arrive with
  their own feature specs. Only the trivial example table is in scope.
- Do not build the test harness/fixtures abstraction (spec 04 owns that). You
  may write minimal DB tests here, but the reusable fixtures live in 04.
- Do not add auth, API features, or frontend.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
