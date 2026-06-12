# Spec 11 — Project model & CRUD API

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **06** (user model) and
   **08** (current-user dependency / auth guards). It also assumes **02**
   (FastAPI app, error handling), **03** (async SQLAlchemy + Alembic) and **04**
   (testing foundation) exist with passing tests.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
   Note: Overleaf embeds the whole file tree inside the Project document; Inkstave
   deliberately does **not** — the tree is a separate relational model in spec 12.
4. **Implement** the backend changes described in `spec.md` (model, schemas,
   repository/service, router, Alembic migration).
5. **Write the tests** listed in the spec's Test plan (unit + integration).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. soft vs.
   hard delete), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 12.

## One-line goal

A signed-in user can create, list, open, rename and delete their own LaTeX
projects through a REST API, each project being an ownable, persisted entity.

## Do NOT (scope guard)

- Do not implement the file tree, folders, documents or files — that is spec 12.
- Do not implement sharing, collaborators or roles — that is spec 33/34.
- Do not implement the dashboard UI — that is spec 16.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
