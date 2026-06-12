# Spec 63 — Runtime Seed & Setup

**Type:** 🟢 feature  ·  **Phase:** 7 — Hardening, packaging & docs (runtime-safety continuation)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: 09 (frontend routing + API
   client + auth context), 57 (bootstrap CLI + `seed_demo` + `/api/setup`
   endpoints). They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the (verified-idempotent) seed coverage and the missing first-run
   `/setup` frontend route described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / route).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 64.

## One-line goal

A fresh instance is immediately usable: the seed command idempotently creates a
demo user + sample multi-file LaTeX project, and a brand-new deployment lands on a
`/setup` page that routes to admin creation.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not change the existing `/api/setup` backend contract — it already exists;
  this spec adds the missing **frontend** `/setup` route that consumes it.
- Do not add real network/LLM/LaTeX compile to tests; the seed and setup tests
  run against the in-process ASGI client / mocked fetch.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
