# Spec 37 — History API (list, diff, restore, labels)

**Type:** 🟢 feature  ·  **Phase:** Phase 5 — Version history  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on **36** (history capture: the
   `history_chunks` / `history_updates` tables, blob offload, and the
   `reconstruct_state` primitive). It also relies on the access-control layer
   (spec 34) for authorising history reads and restores. These must already be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend endpoints: list versions/updates, text diff between
   two versions (and version↔current), restore (non-destructive, applied as a
   CRDT update), and labels/checkpoints CRUD.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. how a
   restore is injected into the live CRDT room), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 38.

## One-line goal

A user (with the right role) can list a document's version history, diff any two
versions, label/checkpoint versions, and restore an old version — all via REST,
with restores applied non-destructively as new CRDT updates.

## Do NOT (scope guard)

- Do not build any history **UI** — that is spec 38.
- Do not change the capture/storage model from spec 36 (read-only consumer, plus
  the two new label/restore concerns).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
