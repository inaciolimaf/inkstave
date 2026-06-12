# Spec 58 — Project Documentation

**Type:** 🟢 feature  ·  **Phase:** Phase 7 — Hardening, packaging & docs  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on **most prior specs** — it
   documents what they built. In particular it relies on **56** (deploy/compose),
   **57** (bootstrap/CI), the compile specs (21–27), collaboration (28–35), the
   AI agent (41–50), and observability/security (51–52). The system should be
   feature-complete enough to describe accurately.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf docs or code** — they
   are AGPLv3 and Inkstave is MIT. Use them only as structural inspiration; write
   original prose about Inkstave's own architecture.
4. **Implement** the documentation set: a polished top-level `README.md`, an
   admin/operations guide, a user guide, an architecture doc, a generated API
   reference, and a `CONTRIBUTING.md` (reiterating the no-Overleaf-code rule),
   all under the locations defined in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (link/anchor checks,
   OpenAPI-export check, presence/section checks). Keep them in-budget.
6. **Verify.** Run the full suite; it must pass and stay under 2 minutes. Then
   check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Note in `docs/` where each document lives and how the API
   reference is regenerated.

When all Definition-of-Done items pass, this spec is complete. Move to spec 59.

## One-line goal

Inkstave ships a complete, navigable documentation set — README, admin/ops guide,
user guide, architecture doc, an OpenAPI-generated API reference, and a
CONTRIBUTING guide — so users, operators and contributors can run, use, and
extend the system.

## Do NOT (scope guard)

- Do not change application behavior, endpoints, or schemas to fit the docs —
  document what exists; file follow-ups for gaps rather than inventing features.
- Do not copy Overleaf documentation, wiki text, or code.
- Do not introduce a heavy docs toolchain; prefer plain Markdown under `docs/`
  plus a generated OpenAPI artifact (see `spec.md`).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
