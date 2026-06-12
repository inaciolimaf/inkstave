# Refactor 30 — Real-time core (specs 28–29)

A hardening pass over the server-side CRDT (28) and the collab WebSocket (29).
**No features, no behaviour change** — two production fixes (a memory leak and a
dead persistence field) plus invariant/regression tests. The layer was built
test-first, so most of the scan is *verified-clean*.

## Baseline (before) → After

| Suite | Before | After |
| --- | --- | --- |
| **Backend** (`pytest backend/tests`, Postgres up) | 463 passed, 1 skipped, ~27 s | **472 passed, 1 skipped, 28.3 s** |
| **Frontend** (`vitest run`) | 207 (unchanged) | 207 (unchanged) |

`ruff` / `mypy` (full, 103 files) clean. New tests are in-process (fake/test Redis
+ test DB), use injected short timers and polling/task-count assertions instead of
sleeps, and add negligible wall time. Combined suite well under 2 minutes.

## Method

A scan→evaluate→apply→verify→record loop over `collab/**` and `collab/ws/**` using
§5.1's checklist (concurrency/races, memory growth, reconnect, persistence
integrity, auth/security, tests/observability). Findings below; each applied fix
ships a regression test that fails on the pre-fix code.

## Findings

| id | area | category | sev | decision | rationale / change |
| --- | --- | --- | --- | --- | --- |
| F-001 | `manager._locks` / `manager.load_count` | **memory growth (B)** | high | **fixed** | A per-document `asyncio.Lock` (and the load counter) was created on first access and **never removed** — the maps grew unbounded with every distinct document ever opened. Eviction now drops the doc's lock + counter *while holding the lock*; `acquire` retries on a lock-identity mismatch so two concurrent acquires still load exactly once across the swap. Tests: `test_locks_and_load_count_bounded_after_eviction`, `test_concurrent_acquire_loads_once`. |
| F-002 | `crdt_document_state.text_synced_seq` | **persistence integrity (D)** | medium | **fixed** | The column existed and `CrdtStore.mark_text_synced` was implemented, but the manager **never called it** — a recovered process couldn't tell whether the persisted spec-13 text was current. `_do_flush_text` now records the flushed seq after a successful bridge write. Test: `test_text_synced_seq_is_maintained`. |
| F-003 | `manager.acquire` single-load | **concurrency (A)** | — | **verified + test** | Per-document load lock is correct (not global); concurrent acquires load once. Strengthened with `test_concurrent_acquire_loads_once` (and the F-001 swap path). |
| F-004 | refcount / eviction | **concurrency (A)** | — | **verified + test** | `release` clamps `max(0, refcount-1)` (never negative); eviction only fires at refcount 0. Tests: `test_refcount_never_negative`, `test_no_eviction_while_connections_remain`. |
| F-005 | compaction high-water mark | **persistence (D)** | — | **verified + test** | append+compact are serialised under the per-doc lock, so the snapshotted state always includes every `id <= upto`; the boundary update is neither lost nor double-applied. Test: `test_compaction_boundary_load_is_exact`. |
| F-006 | content bridge / flush-on-release | **persistence (D)** | — | **verified + test** | The bridge writes content directly (no CRDT re-emit → no loop) and is idempotent (28 tests); `release` force-flushes the final edit. Test: `test_flush_on_release_persists_final_edit`. |
| F-007 | rooms map / Redis subscription teardown | **memory (B)** | — | **verified + test** | Last local leave removes the room and `aclose()`s the subscription; a message to a torn-down room no-ops (`local_broadcast` tolerates a missing room). Test: `test_connect_disconnect_cycles_leave_no_leak`. |
| F-008 | background tasks (writer/forwarder/evict) | **memory (B)** | — | **verified + test** | Writer + forwarder cancelled on cleanup; evict task fires once (cancelled on re-acquire). `test_connect_disconnect_cycles_leave_no_leak` asserts `asyncio.all_tasks()` returns to baseline and `_entries`/`_locks`/rooms/subscriptions empty after repeated cycles. |
| F-009 | reconnect convergence | **reconnect (C)** | — | **verified + test** | A reconnecting client re-runs the stateless sync handshake from its current state vector and receives the missing diff (Step 2). Test: `test_reconnect_resyncs_and_converges`. |
| F-010 | abrupt-disconnect awareness offline | **reconnect (C)** | — | **verified, no change** | The cleanup runs in a `finally`, so the offline awareness update is emitted on abrupt disconnect too (covered by spec-29 `test_awareness_relay_and_offline`, which disconnects without a graceful close). |
| F-011 | origin-exclusion across Redis loopback | **reconnect (C)** | — | **verified, no change** | The envelope carries `(instance_id, origin_conn_id)`; a reconnect gets a fresh `conn_id`, so exclusion stays correct (covered by spec-29 cross-instance test). |
| F-012 | awareness registry races | **concurrency (A)** | — | **verified, no change** | `AwarenessRegistry` methods are fully synchronous (no `await` between read and write), so connections of one document can't interleave mid-method on a single event loop. |
| F-013 | JWT verified before accept | **auth (E)** | — | **verified, no change** | Auth + authz complete *before* `accept()` in the one connect path; the collaborator stub enforces project ownership **and** that the document belongs to the project (spec-29 `test_unknown_document_closes_4404`). |
| F-014 | frame-size + rate limits | **auth (E)** | — | **verified, no change** | Checked on every inbound frame before dispatch (spec-29 oversize/rate-limit tests). |

## Deliberately skipped (with rationale)

- **Apply-then-append ordering** (`handle_update` applies to the CRDT, then
  appends to `crdt_update`) — **skip (low)**. If the append fails after a
  successful apply, the in-memory doc is briefly ahead of the log, but the next
  snapshot (on flush/release/idle) captures the in-memory state, so nothing is
  permanently lost. Reversing the order would risk persisting an update that
  fails to apply (corrupting replay). Current order only persists valid updates.
- **Per-message JWT re-verification / expiry mid-session** — **skip; policy
  decided & documented**: a connection authenticates once at the handshake and is
  **kept until disconnect** (standard for WebSockets; session lifetime is bounded
  by the ASGI server's ping/pong dead-connection detection). Re-verifying every
  frame adds cost for little gain at this stage; finer revocation belongs to a
  later auth spec.
- **App-level ping/pong** — **skip; delegated** to the ASGI server (uvicorn
  `--ws-ping-interval`/`--ws-ping-timeout`), since Starlette doesn't surface WS
  control frames to the application (documented in ADR 0029). `COLLAB_WS_PING_*`
  and close code `4000` are reserved for that layer.
- **Verbose room/compaction logging** — **skip (low)**. The invariants are now
  test-covered; adding structured logs is a noise/value tradeoff better handled by
  the observability spec (51). No new logging added to avoid churn.

## Applied edits

- `collab/manager.py` — bounded `_locks`/`load_count` with a swap-safe `acquire`
  retry loop and eviction cleanup (F-001); `mark_text_synced` after flush (F-002).
- `tests/integration/test_collab_refactor.py` — 7 manager/store invariant tests.
- `tests/integration/test_collab_ws_refactor.py` — reconnect convergence + the
  connect/disconnect leak/bounded-maps test.

No new runtime config; public contracts of specs 28/29 unchanged.
