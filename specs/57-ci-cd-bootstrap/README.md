# Spec 57 — CI/CD & First-Run Bootstrap

**Type:** 🟢 feature  ·  **Phase:** Phase 7 — Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **56** (production images &
   compose), **04** (testing foundation, fixtures, the 2-minute budget, the CI
   skeleton), and **03** (Postgres, async SQLAlchemy, Alembic). They must already
   be implemented and their tests passing. It also touches **06/07** (the User
   model and password hashing) for the admin bootstrap.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the *approach* of run-migrations-on-start and the
   one-time first-admin (launchpad) flow, then write your own.
4. **Implement** the CI pipeline (lint → type-check → unit → integration → e2e,
   enforcing the <2-min budget), the CD/build step for images, safe
   migrations-on-deploy, the first-run admin bootstrap, optional seed data, and
   fail-fast secret/env validation at startup.
5. **Write the tests** listed in the spec's Test plan (bootstrap idempotency, env
   validation, migration-runner safety). Keep them in-budget.
6. **Verify.** Run the full suite. It must pass and stay under 2 minutes. Then
   check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short ADR under `docs/` noting the migration
   strategy (advisory-locked, run-once) and the bootstrap mechanism chosen.

When all Definition-of-Done items pass, this spec is complete. Move to spec 58.

## One-line goal

Inkstave has a CI pipeline that gates merges (lint→type→unit→integration→e2e in
under 2 minutes), a CD build for the Alpine images, migrations that run safely
and once on deploy, a one-time admin-bootstrap for first run, and fail-fast
env/secret validation at startup.

## Do NOT (scope guard)

- Do not author the Dockerfiles/compose/nginx — that is spec **56** (you consume
  them).
- Do not write the user/admin/architecture documentation — that is spec **58**.
- Do not build a full admin panel or invite system — bootstrap creates exactly
  the **first** admin and stops.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
