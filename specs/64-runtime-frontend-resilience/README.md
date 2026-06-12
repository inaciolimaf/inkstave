# Spec 64 — Runtime Frontend Resilience

**Type:** 🟢 feature  ·  **Phase:** 7 — Hardening, packaging & docs (runtime-safety continuation)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: 09 (frontend foundation,
   routing, shadcn/ui), 16/17/18/24/38/46 (the main data views: projects, file
   tree, editor, pdf-preview, history, agent). They must already be implemented
   and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the global app-root error boundary and fill **only the genuinely
   missing** loading/empty/error states identified in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (Vitest + React Testing
   Library).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision, add a short note
   under `docs/`.

When all Definition-of-Done items pass, this spec is complete. This is the last
of the runtime-safety continuation specs (61–64).

## One-line goal

No white screens: a global React error boundary catches render-time throws with a
friendly fallback, and every main data view degrades gracefully with loading,
empty, and error states.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do **not** duplicate states that already exist — most views already have
  loading/empty/error (see the audit in `spec.md`); add only what is missing.
- Do not add `react-error-boundary` (not a dependency); hand-roll a small class
  component (React 19).
- Do not add real network/LLM/LaTeX compile to tests.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
