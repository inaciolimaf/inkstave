# Spec 30 — Refactor pass over the real-time core (CRDT backend + WebSocket)

**Type:** 🔧 refactor  ·  **Phase:** Real-time collaboration  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring spec** — it adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Follow its scan→evaluate→apply
   loop exactly.
2. **Confirm prerequisites.** This spec depends on: **28** (CRDT backend) and
   **29** (collab WebSocket). Both must already be implemented and their tests
   passing. You refactor what those specs built (and any earlier code they touch),
   not greenfield work.
3. **No Overleaf reference.** This spec lists none. Do not copy Overleaf code.
4. **Scan** the real-time core for the problem classes in `spec.md` (races,
   unbounded memory/room growth, reconnect correctness, persistence integrity,
   missing tests, leaks, security gaps).
5. **Evaluate** each finding (risk vs. value) and **apply only the worthwhile
   fixes**, keeping every existing test green and behaviour unchanged unless a
   change is a clear bug fix.
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Add tests for any bug you fix so it cannot regress.
7. **Record decisions.** Write a changelog of what was changed and what was
   deliberately skipped (with reasons) under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 31.

## One-line goal

The CRDT backend and collaboration WebSocket are hardened — no known races,
bounded memory, correct reconnects, intact persistence, and gap-filled tests —
with a recorded changelog and the suite still green and under budget.

## Do NOT (scope guard)

- Do not add new features (no frontend binding/presence UI/sharing — those are
  specs 31+). Behaviour-preserving fixes only, plus tests.
- Do not rewrite the CRDT algorithm or swap libraries; pycrdt stays.
- Do not copy Overleaf code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
