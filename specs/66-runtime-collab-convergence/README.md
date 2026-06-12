# Spec 66 — Runtime safety: two-client collab convergence

**Type:** 🟢 feature (tests-only)  ·  **Phase:** Runtime safety (fast tier)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Implement *exactly* what it describes. This spec adds
   **automated tests only**. If a test surfaces a real CRDT/bridge bug, stop and
   report it rather than editing production code to hide it.
2. **Confirm prerequisites.** Depends on specs **28** (pycrdt `YDocument`,
   `DocumentManager`, `ContentBridge`, protocol framing) and **29** (room manager
   + relay). These exist and pass. Spec **65** (auth/reconnect tests) is a sibling
   that shares the harness.
3. **Study the existing code (for understanding only).** Relevant code lives in
   `backend/src/inkstave/collab/` (`ydocument.py`, `manager.py`,
   `content_bridge.py`, `protocol.py`, `ws/rooms.py`, `ws/router.py`). Do not copy
   Overleaf code — AGPLv3 vs Inkstave MIT.
4. **Write the tests** listed in the spec's Test plan: two pycrdt clients in the
   same process exchanging **binary** y-protocols updates through the server's
   room/relay logic. **No browser, no real network.**
5. **Verify.** Run `just test`. It must pass and stay under the 2-minute budget.
   Check every Acceptance criterion and Definition-of-Done item.
6. **Record decisions.** Note any reusable two-client helper if it establishes a
   new convention.

When all Definition-of-Done items pass, this spec is complete. Move to spec 67.

## One-line goal

Fast, in-process tests prove two collaborators converge to identical text after
concurrent edits, an offline client's queued updates merge cleanly on reconnect,
and the converged text is visible to compile/REST readers via the content bridge.

## Do NOT (scope guard)

- Do not change `collab/` runtime behaviour to make a test pass; report real bugs.
- Do not add a browser, real network sockets, or real Redis to the fast suite.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not implement later-spec features.
