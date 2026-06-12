# Spec 65 — Runtime safety: collab WebSocket auth & reconnect

**Type:** 🟢 feature (tests-only)  ·  **Phase:** Runtime safety (fast tier)  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. This spec adds **automated tests only**; it must
   not change runtime behaviour. If a test reveals a real bug, stop and report it
   rather than silently changing production code.
2. **Confirm prerequisites.** This spec depends on specs **28** (pycrdt model +
   `DocumentManager`), **29** (collab WebSocket endpoint + auth handshake), **34**
   (role→capability access control / viewer read-only), and **08** (JWT auth +
   `authenticate_ws_token`). They are already implemented and their tests pass.
3. **Study the existing code (for understanding only).** This is a from-scratch
   project; the relevant code is in `backend/src/inkstave/collab/ws/` and
   `backend/src/inkstave/auth/`. Do not copy Overleaf code — it is AGPLv3 and
   Inkstave is MIT.
4. **Write the tests** listed in the spec's Test plan. Reuse the existing
   in-process ASGI WebSocket harness at `backend/tests/collab_ws_harness.py`
   (`ASGIWebSocketClient`, `install_collab`, `make_update`, …) and the fake Redis
   fixture. **No real browser, no real network, no real Redis.**
5. **Verify.** Run the full backend suite (`just test`). It must pass and the
   whole suite must stay under the 2-minute budget. Then check every Acceptance
   criterion and Definition-of-Done item.
6. **Record decisions.** If you add a reusable test helper, note it in a short
   `docs/` entry only if it changes a convention.

When all Definition-of-Done items pass, this spec is complete. Move to spec 66.

## One-line goal

Fast, in-process tests prove the collaboration WebSocket rejects bad/missing/
expired auth cleanly (documented close codes, no room joined), that a valid
client re-syncs losslessly after a simulated disconnect, and that a viewer is
strictly read-only.

## Do NOT (scope guard)

- Do not change runtime behaviour of `collab/ws/` or `auth/` to make a test pass;
  if behaviour is wrong, report it.
- Do not add a real browser, real network sockets, or a real Redis to the suite.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not implement features that belong to later specs.
