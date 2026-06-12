# Spec 28 — Server-side CRDT document model (pycrdt)

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **13** (document content
   API/storage — the canonical text this CRDT layer mirrors so REST readers and
   the compiler always see current content). It must already be implemented and
   its tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code** — it is AGPLv3 and Inkstave is MIT. Note
   especially that **Overleaf uses Operational Transformation (ShareJS), not
   CRDT** — its document-updater is a conceptual reference for *holding/flushing
   live doc state*, not for the merge algorithm. Inkstave's CRDT design is its
   own.
4. **Implement** the pycrdt document model, the Yjs sync/update/awareness
   protocol handling, persistence, and the bridge back to spec-13 text — as a
   library, **no HTTP/WebSocket yet**.
5. **Write the tests** listed in the spec's Test plan (unit / integration).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` for the persistence/snapshot
   strategy and the CRDT↔REST bridge.

When all Definition-of-Done items pass, this spec is complete. Move to spec 29.

## One-line goal

The server can hold each document as a Yjs/pycrdt shared-text document, apply and
produce binary Yjs updates, persist CRDT state durably to Postgres, and keep the
spec-13 plain-text content in sync so REST and the compiler see live edits.

## Do NOT (scope guard)

- Do not add the WebSocket transport — that is spec 29.
- Do not add the browser binding or presence UI — specs 31/32.
- Do not implement sharing/authz beyond what spec 13 already enforces — specs
  33/34.
- Do not copy Overleaf code; its OT engine is study-only and a different
  algorithm than Inkstave's CRDT.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
