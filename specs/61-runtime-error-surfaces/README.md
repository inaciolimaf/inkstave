# Spec 61 — Runtime Error Surfaces

**Type:** 🟢 feature  ·  **Phase:** 7 — Hardening, packaging & docs (runtime-safety continuation)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: 02 (error envelope), 09
   (frontend API client), 37 (history diff API), 38 (history UI). They must
   already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the tightly-scoped fix (frontend `getDiff` must map an HTTP 413
   `{too_large:true,...}` response to a structured "diff too large" result
   instead of throwing) plus the tests described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 62.

## One-line goal

The app fails gracefully on the representative HTTP error cases — most concretely,
a too-large history diff (HTTP 413) renders a friendly "too large" state instead
of throwing an unhandled error — and this is locked down by fast automated tests.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not redesign the error-envelope shape or the diff route contract; this spec
  verifies them and fixes only the confirmed 413 client-side mapping bug.
- Do not add real network, real LLM, or real LaTeX compilation to any test here.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
