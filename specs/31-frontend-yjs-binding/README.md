# Spec 31 — Frontend Yjs binding & live sync

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **29** (JWT-authed collab
   WebSocket with rooms and the Yjs sync/update message protocol) and **19**
   (single-user REST autosave and the CodeMirror editor wiring it established on
   top of spec 18). It also assumes **28** (pycrdt server document model and the
   binary Yjs update/sync-step format) exists with passing tests.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Overleaf uses ShareJS/OT, not CRDTs; study only the
   *connection lifecycle and editor-binding approach*, then write your own Yjs
   implementation.
4. **Implement** the frontend changes described in `spec.md`: a Yjs document per
   open project document, a custom WebSocket provider speaking the spec-29
   protocol, the `y-codemirror.next` binding, connect/reconnect/offline
   handling, and the migration away from REST autosave as the live edit channel.
5. **Write the tests** listed in the spec's Test plan (Vitest unit + a minimal
   two-in-process-client collab test + one minimal Playwright two-context e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. how REST
   autosave is retired vs. kept as a fallback), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 32.

## One-line goal

Two browsers editing the same document see each other's keystrokes live, with
edits flowing through Yjs over the spec-29 WebSocket instead of REST autosave,
and surviving disconnect/reconnect without data loss.

## Do NOT (scope guard)

- Do not render remote cursors, selections or an "online now" list — that is
  spec 32 (this spec only carries document text, not awareness/presence UI).
- Do not implement sharing, invites or role-based read-only enforcement — those
  are specs 33 and 34. (You expose a local read-only flag plumbed in spec 34;
  here it is always editable.)
- Do not change the backend CRDT model or WebSocket protocol — consume spec
  28/29 as given.
- Do not copy Overleaf source code (it is OT-based regardless).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`):
  use **Yjs** and **`y-codemirror.next`** only.
