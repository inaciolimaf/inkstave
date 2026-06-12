# Spec 62 — Runtime Config Validation

**Type:** 🟢 feature  ·  **Phase:** 7 — Hardening, packaging & docs (runtime-safety continuation)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: 02 (settings/config module),
   57 (bootstrap CLI: `migrate`, `check-config`, `bootstrap-admin`, `seed`).
   They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the fail-fast required-var validation, the `.env.example`
   de-duplication fix, and the `just doctor` recipe + small CLI described in
   `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 63.

## One-line goal

Misconfiguration fails fast with a clear, human-readable message listing exactly
what is missing/invalid, `.env.example` boots a dev instance out of the box, and
`just doctor` reports config + Postgres/Redis reachability.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not weaken or remove the existing production guards in `config.py`; this
  spec adds a friendly *presentation* layer and a dev-time doctor on top.
- Do not add real external calls in tests — Postgres/Redis reachability checks
  must be mockable and are exercised only against fakes/in-process fixtures.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
