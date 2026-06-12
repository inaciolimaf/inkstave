# Spec 29 — Collaboration WebSocket (JWT-authed rooms + Redis fan-out)

**Type:** 🟢 feature  ·  **Phase:** Real-time collaboration  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **28** (CRDT backend —
   `DocumentManager`, the Yjs protocol codec, awareness registry) and **08**
   (auth guards / sessions — the JWT verification contract and current-user
   resolution). Both must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code** — it is AGPLv3 and Inkstave is MIT. Learn
   the *plumbing*: connection auth, room join/leave, broadcast, and Redis pub/sub
   load-balancing. Inkstave relays binary Yjs (CRDT) messages, not OT ops.
4. **Implement** the FastAPI WebSocket endpoint, room manager, Redis pub/sub
   fan-out, and connection lifecycle described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration with an
   async WS client).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` for the room/pubsub design and
   backpressure policy.

When all Definition-of-Done items pass, this spec is complete. Move to spec 30.

## One-line goal

Multiple browser clients can connect to a JWT-authenticated WebSocket, join a
per-document room, and exchange Yjs sync/update/awareness messages in real time —
correctly relayed even across multiple app instances via Redis pub/sub.

## Do NOT (scope guard)

- Do not implement the CRDT merge/persistence — that is spec 28 (drive it).
- Do not implement the browser binding (spec 31) or presence UI (spec 32).
- Do not implement sharing/roles or full access control — beyond an "is a
  collaborator" stub, that is specs 33/34.
- Do not copy Overleaf code; `real-time` is plumbing study only.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
