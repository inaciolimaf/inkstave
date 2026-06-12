# Spec 01 — Project Scaffolding

**Type:** 🟢 feature  ·  **Phase:** Phase 0 — Foundations  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **none** (it is the first).
   It establishes the repository skeleton every later spec adds to.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach (monorepo layout, compose
   orchestration, dev tooling), then write your own implementation.
4. **Implement** the directory layout, tooling configuration, base
   `docker-compose.yml`, `.env.example`, `LICENSE`, command runner and
   pre-commit hooks described in `spec.md`. **No application/feature code.**
5. **Write the tests** listed in the spec's Test plan (here: a tiny smoke test
   per tool surface plus a CI-less local verification — see §8).
6. **Verify.** Run the verification commands in the spec. The whole future test
   suite must stay under the 2-minute budget; this spec adds essentially no
   runtime. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short ADR under `docs/` noting the choice of `uv`
   + `pnpm` and the command-runner choice.

When all Definition-of-Done items pass, this spec is complete. Move to spec 02.

## One-line goal

After this spec the repository has a clean, conventional monorepo layout with
Python (`uv`) and Node (`pnpm`) tooling, a base `docker-compose.yml` running
Postgres + Redis, a documented `.env.example`, an MIT `LICENSE`, and a
command runner — so every subsequent spec has a defined place to add code.

## Do NOT (scope guard)

- Do not create the FastAPI app or any backend Python modules (that is spec 02).
- Do not create the React app or any frontend source (that is spec 09).
- Do not add database models, migrations, or Alembic (spec 03).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
