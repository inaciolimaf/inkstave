# Spec 66 — Runtime safety: two-client collab convergence (requirements)

## 1. Summary

This spec adds **automated runtime-safety tests** (no new product features) that
prove Inkstave's CRDT collaboration actually converges. Two `pycrdt` clients live
in the **same process** and exchange **binary** y-protocols updates through the
server's real relay path (`DocumentManager` + `RoomManager` / the WS endpoint).
The tests pin three guarantees: (a) two clients applying *concurrent* edits to the
same document converge to byte-identical text after they exchange updates; (b) an
"offline" client whose updates were queued while disconnected merges them
losslessly on reconnect, and both ends converge; (c) the CRDT→`documents.content`
bridge reflects the converged text, so the Tectonic compiler and REST readers see
current content. No browser, no real network, fake Redis only.

## 2. Context & dependencies

- **Depends on:**
  - Spec **28** — `YDocument` (`backend/src/inkstave/collab/ydocument.py`),
    `DocumentManager` (`collab/manager.py`), `ContentBridge`
    (`collab/content_bridge.py`), and the y-protocols framing
    (`collab/protocol.py`: `read_message`, `encode_update`, `encode_sync_step1/2`).
  - Spec **29** — `RoomManager.local_broadcast` (`collab/ws/rooms.py`) and the
    relay/dispatch in `collab/ws/router.py`.
  - Spec **13** — `documents.content` column + `read_content_for_collab` /
    `set_content_from_collab` (`services/document_service.py`) the bridge writes to.
- **Unlocks:** Confidence for compile/history features that read converged text.
- **Affected areas:** backend tests only (`backend/tests/`). No production code,
  no migrations, no frontend.

## 3. Goals

- Prove **concurrent convergence**: two pycrdt `Doc`s make independent edits, the
  server applies/relays both, and after exchange both client docs *and* the
  server's `YDocument` hold identical text and identical CRDT state vectors.
- Prove **offline-merge on reconnect**: a client makes edits while "disconnected"
  (its updates buffered, not sent); on reconnect it replays them and exchanges a
  sync step with the server; no edit is lost or duplicated and both ends converge.
- Prove the **content bridge** reflects the converged text: after a flush,
  `documents.content` (read via `read_content_for_collab` / a REST read) equals the
  converged document text that a compile job would consume.
- Keep convergence assertions **deterministic** — assert on final text equality
  and state-vector equality, independent of edit interleaving order.

## 4. Non-goals (explicitly out of scope)

- No browser / `y-codemirror.next` binding (frontend spec 31; e2e spec 54).
- No real cross-instance Redis fan-out (single in-process instance + fake Redis).
- No awareness/presence convergence (spec 32 has its own coverage); this spec is
  about *document state* convergence.
- No changes to CRDT merge semantics, the bridge, or the relay; tests only observe.

## 5. Detailed requirements

### 5.1 Data model (if any)

None new. Tests use existing `Project`, `TreeEntity`/`Document`, `CrdtUpdate` via
factories/services. The bridge writes the converged text to `documents.content`.

### 5.2 Backend / API (if any)

No new endpoints/contracts. Systems under test (do not change them):

- `YDocument` (`collab/ydocument.py`): `replace_text`, `apply_update(update,
  origin=...)`, `observe(cb)`, `get_state()`, `get_state_vector()`, `diff(sv)`,
  and the `.text` property. Two independent `YDocument`/pycrdt `Doc` instances are
  the two "clients".
- `DocumentManager` (`collab/manager.py`):
  - `acquire(document_id)` / `release(document_id)` — lifecycle/refcount.
  - `handle_sync_step1(doc_id, state_vector)` → `(sync_step2_for_client,
    server_step1)`.
  - `handle_update(doc_id, update, origin)` → returns the raw update to relay;
    applies + persists + schedules a text-bridge flush.
  - `current_text(doc_id)` — the live authoritative text (loads if idle).
  - `flush(doc_id)` — force the bridge + compact.
- `RoomManager.local_broadcast(document_id, payload, exclude)` — fan-out to local
  connections, excluding the origin (so a client never receives its own echo).

### 5.3 Frontend / UI (if any)

None.

### 5.4 Real-time / jobs / external integrations (if any)

- **Two-client relay model.** Two ways to drive convergence; the spec requires at
  least the manager-level path and at least one full-endpoint path:
  1. **Manager-level (preferred for determinism):** create two pycrdt client
     docs; for each client edit, capture the emitted binary update via
     `observe`, hand it to `manager.handle_update(doc_id, update, origin=clientId)`,
     then relay the returned bytes to the *other* client by `apply_update`. Drive
     the sync handshake with `handle_sync_step1` for the reconnect case.
  2. **Endpoint-level:** two `ASGIWebSocketClient`s (from
     `backend/tests/collab_ws_harness.py`) in the same room; use `make_update` to
     send `SyncUpdate`s and `apply_update_message` to apply relayed bytes into a
     local `YDocument`. This exercises `router.py` + `RoomManager` end-to-end.
- **Offline simulation.** Buffer a client's updates in a list while it is
  "disconnected" (do not relay them). On "reconnect": send `SyncStep1` (state
  vector), apply the server's `SyncStep2`, then replay the buffered updates through
  `handle_update`, and relay the server's responses back. Convergence is asserted
  after the exchange settles.
- **Bridge flush.** The bridge flush is debounced
  (`collab_text_flush_debounce_ms`, default 1000 ms). For fast assertions either
  call `manager.flush(doc_id)` explicitly or install collab with
  `collab_text_flush_debounce_ms=10`. Never block the suite on the 1 s default.
- **Redis:** fake Redis fixture (`redis` in conftest); `install_collab(...)` for
  the endpoint-level path.

### 5.5 Configuration

No new env vars. Tests may override `collab_text_flush_debounce_ms` and
`collab_snapshot_every_updates` via `install_collab(..., **overrides)` for speed
and to exercise compaction; document the override inline.

## 6. Overleaf reference (study only — never copy)

> Inkstave shares no code with Overleaf; this is an independent implementation.

- `services/document-updater/` (Overleaf) — conceptual reference only for "two
  editors, one document, converge". Overleaf uses OT/ShareJS; Inkstave uses
  CRDT/pycrdt — the merge model is fundamentally different. **Do not** copy or
  translate. The convergence guarantee here comes from pycrdt's CRDT semantics,
  implemented under Inkstave's own specs 28/29.

## 7. Acceptance criteria

1. **Given** two pycrdt client docs synced from the same empty server document,
   **when** client A inserts `"Hello "` and client B inserts `"World"` *without
   first seeing each other's edit* (concurrent), and both updates are relayed
   through the server to the other client, **then** after exchange A.text ==
   B.text == server text, and A and B have equal state vectors.
2. **Given** AC1's convergence, **then** the converged text contains both
   `"Hello "` and `"World"` (each exactly once) — no edit dropped, none duplicated.
3. **Given** a converged document, **when** the same updates are replayed again
   (idempotency check), **then** the text is unchanged — applying an already-seen
   CRDT update is a no-op.
4. **Given** a connected client A and an "offline" client B that makes 3 edits
   while disconnected, **when** B reconnects and exchanges a sync step + replays
   its buffered updates, **then** A.text == B.text == server text and all of B's
   3 edits are present (offline-merge, no loss).
5. **Given** B was offline and A also edited during that window, **when** B
   reconnects, **then** B's synced document includes A's interim edit too (two-way
   merge on reconnect).
6. **Given** any converged state above, **when** the manager flushes the text
   bridge (`flush` or a tiny debounce), **then** `read_content_for_collab(session,
   doc_id)` (and a REST document read, if exercised) returns exactly the converged
   server text — what a compile job would consume.
7. **Given** the endpoint-level path, **when** an editor sends an update, **then**
   the *other* connection receives the relayed `SyncUpdate` but the **origin**
   connection does not receive its own echo (`local_broadcast` excludes origin).
8. **Given** every test in this spec, **then** it makes **no real network call,
   uses no real Redis, and starts no browser** — two in-process pycrdt clients +
   the real server relay + fake Redis + transactional DB only.

## 8. Test plan

> All tests combined must keep the suite under 2 minutes. These are CPU-light
> in-process CRDT exchanges; each test should add only a few milliseconds.

- **Integration (pytest + manager/endpoint + fake Redis + test DB)** — new file
  `backend/tests/integration/test_runtime_collab_convergence.py`, marked
  `pytestmark = pytest.mark.integration`:
  - `test_concurrent_edits_converge` (AC1–AC3) — manager-level: two client
    `YDocument`s, capture updates via `observe`, relay through `handle_update`,
    assert text + state-vector equality and idempotent replay.
  - `test_offline_client_merges_on_reconnect` (AC4–AC5) — buffer B's updates
    offline; on reconnect drive `handle_sync_step1` + replay; assert two-way merge.
  - `test_converged_text_visible_to_bridge` (AC6) — after convergence,
    `manager.flush(doc_id)` then assert `read_content_for_collab` / a REST read
    equals the server text; install collab with `collab_text_flush_debounce_ms=10`.
  - `test_relay_excludes_origin` (AC7) — endpoint-level with two
    `ASGIWebSocketClient`s: the sender uses `expect_no_message` to confirm no
    self-echo while the peer receives the relayed bytes.
- **Unit (pytest):** optionally a focused `YDocument`-only convergence test (two
  `Doc`s, no DB) to document the CRDT property cheaply.
- **E2E (Playwright):** none here (two-browser convergence belongs to spec 54 and
  must not enter the fast tier).
- **Performance/budget note:** all exchanges are synchronous in-process; replace
  any debounce wait with an explicit `manager.flush` or a 10 ms override so the
  file adds well under a second.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (tests written; no production change).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; run via `just test`.
- [ ] **Full suite still runs in < 2 minutes.**
- [ ] **No real external calls** (no real network, no real Redis, no browser) in
      any automated test added here.
- [ ] `ruff format` / `ruff check` / `mypy` clean on the new test file.
- [ ] No Overleaf code copied.
- [ ] Any real convergence/bridge bug surfaced is reported, not hidden by a
      production edit.
