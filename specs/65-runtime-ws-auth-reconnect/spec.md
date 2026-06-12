# Spec 65 — Runtime safety: collab WebSocket auth & reconnect (requirements)

## 1. Summary

This spec adds **automated runtime-safety tests** (no new product features) that
exercise the collaboration WebSocket end-to-end, in-process, on the FastAPI app.
It pins three guarantees that protect every collaborative session: (a) a
connection with a missing, malformed, or **expired** JWT is rejected with the
documented close code and never joins a room or receives any document data; (b) a
valid client completes the sync handshake, and after a *simulated* disconnect a
fresh connection re-syncs losslessly (no lost or duplicated state); (c) a viewer
joins read-only — the server silently drops the viewer's CRDT writes while still
relaying others' edits. All tests run on the in-process ASGI WebSocket client
against fake Redis; there is no real browser and no real network.

## 2. Context & dependencies

- **Depends on:**
  - Spec **08** — JWT auth and `authenticate_ws_token`
    (`backend/src/inkstave/auth/dependencies.py`, `auth/tokens.py`).
  - Spec **28** — pycrdt `DocumentManager` + sync protocol
    (`backend/src/inkstave/collab/manager.py`, `collab/protocol.py`,
    `collab/ydocument.py`).
  - Spec **29** — collab WebSocket endpoint + handshake + close codes
    (`backend/src/inkstave/collab/ws/router.py`, `ws/rooms.py`, `ws/components.py`).
  - Spec **34** — role→capability access control / viewer read-only
    (`backend/src/inkstave/authorization/`).
- **Unlocks:** Spec **66** (collab convergence tests) reuses the same harness;
  this spec hardens the auth/reconnect edges that 66 assumes hold.
- **Affected areas:** backend tests only (`backend/tests/`). No production code,
  no migrations, no frontend.

## 3. Goals

- Prove the WS auth handshake rejects **missing**, **malformed**, and **expired**
  tokens with the exact documented close codes, *before* `websocket.accept()`,
  with no document bytes ever sent.
- Prove a rejected connection never becomes a room member (room count stays 0;
  the `DocumentManager` is never `acquire`d for that connection).
- Prove a valid editor completes the sync handshake and that, after a simulated
  disconnect, a *new* connection by the same user re-syncs the full converged
  text with no loss and no duplication (idempotent replay of sync step 2).
- Prove a viewer (spec 34) joins but is strictly read-only: its `SyncUpdate`/
  `SyncStep2` frames are dropped (nothing applied, persisted, or broadcast),
  while it still receives editor updates and awareness.

## 4. Non-goals (explicitly out of scope)

- No Playwright / real-browser reconnect test (that lives in the e2e suite,
  spec 54; it must stay out of the fast tier).
- No real Redis pub/sub across two app instances (cross-instance fan-out already
  has coverage; here a single in-process instance + fake Redis is sufficient).
- No changes to close codes, the handshake, or the read-only enforcement; this
  spec only *observes* them. If they are wrong, report rather than edit.
- No token-refresh / re-auth-mid-connection flow (not implemented for WS).

## 5. Detailed requirements

### 5.1 Data model (if any)

None. Tests use the existing `User`, `Project`, `ProjectMembership`,
`TreeEntity`/`Document`, and `CrdtUpdate` models via the existing factories
(`backend/tests/factories.py`) and services (`create_project`, `create_entity`,
`set_content_from_collab`).

### 5.2 Backend / API (if any)

No new endpoints. The system under test is the existing endpoint:

```
@router.websocket("/ws/collab/projects/{project_id}/documents/{document_id}")
```

defined in `backend/src/inkstave/collab/ws/router.py`. Current, authoritative
behaviour the tests must lock in (do not change it):

- The access token arrives as the `?token=` query param. Auth + authorization run
  **before** `websocket.accept()`:
  - no token → `await websocket.close(code=CLOSE_UNAUTHORIZED)` = **4401**;
  - `authenticate_ws_token` raises (malformed/expired/unknown user) → **4401**;
  - unknown/deleted project or unknown document → `CLOSE_NOT_FOUND` = **4404**;
  - authenticated non-member → `CLOSE_FORBIDDEN` = **4403**.
  Close codes are defined in `backend/src/inkstave/collab/ws/rooms.py`
  (`CLOSE_UNAUTHORIZED=4401`, `CLOSE_FORBIDDEN=4403`, `CLOSE_NOT_FOUND=4404`).
- On accept, the server enqueues its half of the handshake:
  `encode_sync_step1(handle.ydoc.get_state_vector())` then, if present, an
  awareness snapshot. The client replies with `SyncStep1`; the server answers
  `handle_sync_step1` → `(sync_step2_for_client, server_step1)`.
- Viewer enforcement (`_dispatch` in `router.py`): when `conn.can_write` is False,
  inbound `SyncStep2`/`SyncUpdate` frames `return True` immediately — never
  applied, persisted, or published. `can_write` derives from
  `Capability.COLLAB_WRITE in capabilities_for(role)`.

### 5.3 Frontend / UI (if any)

None.

### 5.4 Real-time / jobs / external integrations (if any)

- **Transport under test:** the in-process ASGI WebSocket client
  `ASGIWebSocketClient` in `backend/tests/collab_ws_harness.py`, driving the app
  over the raw ASGI protocol on the test event loop (so the shared transactional
  DB session works). Its API: `expect_accept()`, `receive_bytes()`,
  `close_code()`, `expect_no_message()`, `send_bytes()`, `disconnect()`, and the
  async context manager that issues `websocket.connect` on enter and
  `websocket.disconnect` on exit.
- **Redis:** the `redis` fixture in `backend/tests/conftest.py` (fakeredis,
  flushed per test). Wire components with `install_collab(app, db_session, redis)`.
- **Disconnect simulation:** call `await ws.disconnect()` (or exit the
  `async with` block) to push a `websocket.disconnect` frame; the endpoint's
  `_receive_loop` returns and `_cleanup` runs (`manager.release`, room leave,
  awareness removal). A *new* `ASGIWebSocketClient` then re-runs the handshake.
- **Expired token:** build a `TokenService` from a `Settings(_env_file=None,
  access_token_ttl_seconds=-1)` (or a tiny positive TTL) so `create_access_token`
  emits an already-expired `exp`; pass that token in `?token=`. The server-side
  decode (in `authenticate_ws_token`) uses the app's normal settings, so it
  rejects the expired token via `TokenError` → 4401. Alternatively sign claims
  directly with a past `exp` using the same `jwt_secret`.

### 5.5 Configuration

No new env vars. Tests may pass `install_collab(..., **overrides)` to tune collab
settings (e.g. `collab_text_flush_debounce_ms=10`) so a flush/persist assertion
resolves quickly without `sleep`-ing near the 2-minute budget. Document any such
override inline in the test.

## 6. Overleaf reference (study only — never copy)

> Inkstave shares no code with Overleaf; this is an independent implementation.

- `services/document-updater/` and `services/real-time/` (Overleaf) — only as a
  conceptual reference for how a collaborative editor reconnects and re-syncs
  after a dropped socket. **Do not** copy or translate any of it. Inkstave's
  realtime layer is pycrdt + a custom y-protocols framing, unrelated to Overleaf's
  ShareJS/OT design. This capability is implemented from Inkstave's own specs 28/29.

## 7. Acceptance criteria

1. **Given** the app with collab installed and a valid document, **when** a client
   connects with **no** `?token=`, **then** the first frame received is
   `websocket.close` with code **4401**, and no `websocket.accept` or any
   `websocket.send` precedes it.
2. **Given** a valid document, **when** a client connects with a **malformed**
   token (`token=not-a-jwt`), **then** it is closed with **4401** before accept.
3. **Given** a valid user and document, **when** the client connects with an
   **expired** access token, **then** it is closed with **4401** before accept
   (proving expiry is enforced, not just signature).
4. **Given** any rejected connection (criteria 1–3), **then** the `RoomManager`
   reports `room_count() == 0` for the document and the `DocumentManager` was
   never acquired for it (e.g. `manager.load_count` has no entry for the doc).
5. **Given** an authenticated **non-member**, **when** they connect to an existing
   project/document, **then** they are closed with **4403**; **and** given a
   random unknown project/document id with a valid token, the close code is
   **4404**.
6. **Given** a valid editor that has joined and seeded document text `"alpha"`,
   **when** the socket disconnects and the **same** user opens a **new**
   connection and completes the handshake, **then** the new connection's sync
   step 2 reconstructs exactly `"alpha"` — no characters lost and no characters
   duplicated (text equals `"alpha"`, length unchanged).
7. **Given** two editors A and B in the same room, A writes `"X"` then
   disconnects; B writes `"Y"`; A reconnects, **then** A's post-reconnect synced
   document contains both `"X"` and `"Y"` exactly once each (convergence after a
   drop; no duplication of A's own earlier edit).
8. **Given** a **viewer** connection (spec 34), **when** it sends a `SyncUpdate`,
   **then** no `CrdtUpdate` row is persisted for that document and no update is
   broadcast to other connections; **and** when an editor in the same room writes,
   the viewer still receives that relayed update.
9. **Given** any test in this spec, **then** it performs **no real network call,
   no real Redis, and no real browser** — only the in-process ASGI client + fake
   Redis + transactional test DB.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> These tests are I/O-light (in-process ASGI, fake Redis, rolled-back DB).

- **Integration (pytest + httpx ASGI WS harness + fake Redis + test DB)** — new
  file `backend/tests/integration/test_runtime_ws_auth_reconnect.py`, marked
  `pytestmark = pytest.mark.integration`:
  - `test_missing_token_rejected_4401_no_room` (AC1, AC4) — assert close code,
    assert `components.rooms.room_count() == 0` and the doc id absent from
    `components.manager.load_count`.
  - `test_malformed_token_rejected_4401` (AC2).
  - `test_expired_token_rejected_4401` (AC3) — craft the expired token via a
    `TokenService` built from `Settings(access_token_ttl_seconds=-1)`.
  - `test_non_member_4403_and_unknown_4404` (AC5).
  - `test_reconnect_resyncs_seeded_text_losslessly` (AC6) — seed `"alpha"` via
    `set_content_from_collab`; editor joins, disconnects; new editor connection
    sends `SyncStep1` with an empty state vector, receives `SyncStep2`, applies it
    into a local `YDocument`, asserts text `== "alpha"`.
  - `test_two_editors_converge_after_drop` (AC7) — drive two `ASGIWebSocketClient`s
    via `make_update`; after A reconnects, the synced text contains both edits
    once each. (Keep timing tight; use `expect_*`/`receive_bytes` with the default
    2 s timeout, never long sleeps.)
  - `test_viewer_write_dropped_but_reads` (AC8) — reuse the membership setup from
    `test_collab_ws_access.py`; assert `CrdtUpdate` count `== 0` after a viewer
    write and that the viewer receives a relayed editor update.
- **Unit (pytest):** none strictly required; the handshake/close-code constants
  already have unit coverage. Optionally add a focused unit test asserting that an
  expired token raises `TokenError` from `TokenService.decode_token` to document
  the mechanism (fast, no app).
- **E2E (Playwright):** none in this spec (browser reconnect lives in spec 54 and
  must not enter the fast tier).
- **Performance/budget note:** every test runs in-process with fake Redis and a
  rolled-back transaction; replace any `sleep` with `expect_no_message(0.05)` or a
  small flush-debounce override so the file adds well under a second to the suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (tests written; no production change).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; run via `just test`.
- [ ] **Full suite still runs in < 2 minutes.**
- [ ] **No real external calls** (no real network, no real Redis, no real
      browser) in any automated test added here.
- [ ] `ruff format` / `ruff check` / `mypy` clean on the new test file.
- [ ] No Overleaf code copied.
- [ ] If any test exposes a real bug in `collab/ws/` or `auth/`, it is reported
      (not papered over by editing production code).
