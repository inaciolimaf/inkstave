# Spec 02 — Backend Foundation

**Type:** 🟢 feature  ·  **Phase:** Phase 0 — Foundations  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **01** (monorepo layout,
   `backend/` `uv` project, base `docker-compose.yml` with Postgres + Redis,
   `.env.example`). Spec 01 must be implemented and its checks passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn how app wiring, settings, logging and error
   handling are *approached*, then write your own FastAPI implementation.
4. **Implement** the FastAPI application factory, Pydantic-settings config,
   structured JSON logging, global exception handlers + error envelope,
   `/health` and `/ready` endpoints, CORS, `/api/v1` versioning, the Redis
   connection provider, app lifespan, and DI conventions described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit + integration with
   `httpx.AsyncClient`). Redis is **faked** in tests; nothing slow runs.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` if you make an architectural
   choice (e.g. logging library, settings layout, error-envelope shape).

When all Definition-of-Done items pass, this spec is complete. Move to spec 03.

## One-line goal

After this spec there is a runnable FastAPI app skeleton with environment-driven
settings, structured JSON logging, a uniform error envelope, `/health` and
`/ready` endpoints, CORS, an `/api/v1` router, a Redis provider, and a clean
lifespan — ready for the database layer (03) and features to plug in.

## Do NOT (scope guard)

- Do not add SQLAlchemy, Alembic, or any database models/sessions (spec 03).
- Do not implement auth, users, or JWT (specs 06–08).
- Do not implement ARQ workers or job definitions (spec 22 onward) — only the
  Redis *connection provider* is in scope here.
- Do not build any frontend (spec 09).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
