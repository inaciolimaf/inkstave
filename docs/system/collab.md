# Collaboration

Real-time co-editing of one document. Browsers hold a Yjs document bound to CodeMirror and talk to a
per-document WebSocket room; the server keeps an authoritative `pycrdt` copy, persists every update to
Postgres, fans messages out through Redis and writes the merged text back to `documents.content`, which
REST readers, compile and the agent read. Presence (cursors, names) travels on the same socket and is
never stored. It came from specs 28 (CRDT model), 29 (transport), 30 and 34 (roles), with later fixes in
65, 66 and 74. The module is `backend/src/inkstave/modules/collab`.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/collab/__init__.py` | Public surface: `YDocument`, `encode_update`, `flush_open_project_docs`, the two models |
| `backend/src/inkstave/modules/collab/models.py` | `CrdtDocumentState`, `CrdtUpdate` |
| `backend/src/inkstave/modules/collab/crdt/ydocument.py` | `YDocument`: a `pycrdt.Doc` with one shared text, root key `content` |
| `backend/src/inkstave/modules/collab/crdt/protocol.py` | y-protocols framing: `read_message`, `encode_sync_step1`, `encode_sync_step2`, `encode_update`, `encode_awareness` |
| `backend/src/inkstave/modules/collab/crdt/awareness.py` | `AwarenessRegistry`, in-memory presence per document |
| `backend/src/inkstave/modules/collab/crdt/state.py` | `CollabSettings`, `UpdateTooLargeError`, `_Entry`, `OpenDocument` |
| `backend/src/inkstave/modules/collab/rooms/manager.py` | `DocumentManager`: refcounted in-memory documents, flush, compaction, eviction |
| `backend/src/inkstave/modules/collab/rooms/store.py` | `CrdtStore`: snapshot plus append-only log |
| `backend/src/inkstave/modules/collab/rooms/content_bridge.py` | `ContentBridge`: CRDT text to and from `documents.content` |
| `backend/src/inkstave/modules/collab/rooms/flush.py` | `flush_open_project_docs`: forced flush before a worker job reads content |
| `backend/src/inkstave/modules/collab/ws/router.py` | `collab_ws` endpoint, `_admit`, `_join_room`, `_handshake`, `_serve` |
| `backend/src/inkstave/modules/collab/ws/connection.py` | `_authorize`, `_writer`, `_force_close`, `_make_forwarder`, `_cleanup` |
| `backend/src/inkstave/modules/collab/ws/messaging.py` | `_receive_loop`, `_frame_rejection`, `_dispatch`, `_RateLimiter` |
| `backend/src/inkstave/modules/collab/ws/rooms.py` | Close codes, `Connection`, `Room`, `RoomManager` |
| `backend/src/inkstave/modules/collab/ws/redis_bridge.py` | `RedisBridge`, the binary envelope, `Subscription` |
| `backend/src/inkstave/modules/collab/ws/components.py` | `CollabComponents`, `CollabWsSettings`, `build_collab_components` |
| `backend/src/inkstave/app.py` | Builds the components onto `app.state.collab`, closes them on shutdown |
| `frontend/src/modules/collab/InkstaveWsProvider.ts` | Browser provider: sync, awareness, reconnect, terminal close codes |
| `frontend/src/modules/collab/useCollabDoc.ts` | React lifecycle of one collaborative document. Builds the `Y.UndoManager([text, suggestions])` and the editor extensions, and returns the `SuggestController` |
| `frontend/src/modules/collab/suggestions/model.ts` | Suggestion records, relative positions (`encodePosition`, `resolvePosition`), `readSuggestions`, `ownInsertions`, `newSuggestionId` (spec 119) |
| `frontend/src/modules/collab/suggestions/record.ts` | `planEdit`: the rules of spec 119 §5.2 as a pure planner over one edit |
| `frontend/src/modules/collab/suggestions/suggest-extension.ts` | `suggestExtension`: the Inkstave sync plugin that replaces `ySync`, the refusal of an oversize deletion, `SuggestController` |
| `frontend/src/modules/collab/suggestions/review.ts` | `decideSuggestion`, `decideAllSuggestions`: accept and reject, origin `review-decision` |
| `frontend/src/modules/collab/suggestions/decorations.ts` | The underline, the folded deletion widget and their theme |
| `frontend/src/modules/collab/suggestions/popover.ts` | The hover popover of a suggestion: author, time, Accept and Reject |
| `frontend/src/modules/collab/suggestions/use-suggestion-list.ts` | `useSuggestionList`: the rows of the Suggestions tab, kept in step with the text |
| `frontend/src/modules/collab/suggestions/api.ts` | `setSuggestMode`: `PATCH /api/v1/projects/{id}/me` |
| `frontend/src/modules/collab/usePresence.ts` | Presence state for the UI |
| `backend/tests/collab_ws_harness.py` | In-process ASGI WebSocket client and `install_collab` |
| `frontend/e2e/flows/collab.spec.ts` | End-to-end co-editing |

`collab/README.md` only points here: that directory holds no code.

Wiring: `build_collab_components` imports `HistoryCaptureService` from `inkstave.modules.history` and
creates it when `HISTORY_CAPTURE_ENABLED` is true, stored as `CollabComponents.history`. `history` in turn
imports `YDocument`, `CrdtDocumentState`, `CrdtUpdate` and `encode_update` from
`inkstave.modules.collab`, so the two modules depend on each other at module load, and restore reaches back
through `CollabComponents`. See [history.md](history.md).

## Data

Migration: `backend/migrations/versions/20260609_2310_b7c4e9d21f08_create_crdt_tables.py`.

| Table | Columns | Notes |
|---|---|---|
| `crdt_document_state` | `document_id` PK, `state`, `state_vector`, `seq`, `text_synced_seq`, `updated_at` | 1:1 with `documents.entity_id`, cascade delete. `seq` rises on every snapshot |
| `crdt_update` | `id` bigint PK, `document_id`, `update`, `origin`, `created_at` | Append-only log between snapshots, index `ix_crdt_update_document_id_id`, cascade delete. `origin` is the connection id, or `restore-<hex>` for a restore |

Redis holds only pub/sub traffic, one channel per document, `COLLAB_REDIS_CHANNEL_PREFIX` plus the document
id. Nothing is stored there. Awareness, rooms, `YDocument` copies and send queues are process memory.

### Suggestions (spec 119)

The `Y.Doc` has a second root type besides the text: `Y.Map("suggestions")`, keyed by a UUIDv7 suggestion id.
An insertion stores `{kind: "insert", author_id, author_name, created_at, start, end}` and a deletion stores
`{kind: "delete", author_id, author_name, created_at, at, text}`. The positions are base64 Yjs relative
positions. The server stores and relays it inside the same state as the text, so snapshots, the log and reloads
keep it with no server code; `YDocument.suggestions()` reads it, for the tests only. `documents.content` is written
from the text alone, so nothing outside the editor sees a suggestion: compile and the agent read the suggested
text.

The text change and its record are one Yjs transaction, with the editor's sync origin, so one undo reverts
both. `y-codemirror.next`'s own sync plugin cannot do that, so Suggesting mode replaces it (ADR 0119 has the
spike). The library's undo plugin, remote cursors and undo keymap stay. Accept and reject run in their own
transaction with the origin `review-decision`, which no undo manager tracks.

## Routes

There are no REST routes. One WebSocket, mounted at the root and not under `/api/v1`:

`/ws/collab/projects/{project_id}/documents/{document_id}?token=<access token>`

The token is a query parameter because browsers cannot set headers on `WebSocket`.

Close codes, from `backend/src/inkstave/modules/collab/ws/rooms.py`:

| Code | Name | When |
|---|---|---|
| 4000 | `CLOSE_DEAD` | `app.state.collab` is `None` (database or Redis not wired). Named "ping timeout" in the source, but the server has no ping logic |
| 4400 | `CLOSE_BAD_MESSAGE` | Text frame, frame over `COLLAB_WS_MAX_FRAME_BYTES`, or update over `COLLAB_MAX_UPDATE_BYTES` |
| 4401 | `CLOSE_UNAUTHORIZED` | Token missing, invalid, expired, or `is_alive` refused it |
| 4403 | `CLOSE_FORBIDDEN` | Authenticated, project exists, no membership |
| 4404 | `CLOSE_NOT_FOUND` | Unknown or soft-deleted project; unknown id or non-doc entity |
| 4408 | `CLOSE_SLOW_CONSUMER` | Send queue full when the Redis forwarder enqueues |
| 4429 | `CLOSE_RATE_LIMITED` | More than `COLLAB_WS_MAX_MSGS_PER_SEC` messages in the current one-second window |

`CLOSE_NORMAL` (1000) is defined and never used. 4000, 4401, 4403 and 4404 are all sent before `accept()`;
see Points of attention for what the browser sees.

Wire format is the standard y-protocols encoding: outer tag 0 for sync (sub-types step 1, step 2, update),
1 for awareness. Unknown or malformed input decodes to `UnknownMessage` and is ignored.

## How it works

### Join

1. `collab_ws` returns 4000 if `app.state.collab` is missing and 4401 if no token.
2. `_admit` runs before `accept()`: `authenticate_ws_token` (the same `_resolve_user` and `is_alive` as
   `get_current_user`), then `_authorize`. `_authorize` loads the project, calls `role_for`, calls
   `get_entity` with `TreeEntityType.doc`, and computes `can_write` as
   `Capability.COLLAB_WRITE in capabilities_for(role)`. Owner and editor write; viewer reads.
3. A non-auth exception from step 2 propagates rather than becoming a 4401.
4. After `accept()` the endpoint builds a `Connection` with a queue of `COLLAB_WS_SEND_QUEUE_MAX`, binds
   log context, and runs `_serve` inside `track_ws("collab")`.
5. `_join_room` calls `DocumentManager.acquire`, joins the local `Room`, and subscribes to Redis if this
   connection created the room.
6. `_serve` starts the `_writer` task, then `_handshake` enqueues the server's step 1 and the awareness
   snapshot, then `_receive_loop` runs until disconnect or a forced close.

### Inbound messages

`_receive_loop` rejects with `_frame_rejection` (text frame, oversize, rate) and otherwise hands the parsed
message to `_dispatch`:

- `SyncStep1`: `_handle_step1` answers with step 2 and does not resend the server's step 1.
- `SyncStep2` or `SyncUpdate`: `_handle_update`. A viewer's update returns early, with no apply, persist,
  relay or capture, and the socket stays open. Otherwise `DocumentManager.handle_update` applies it,
  appends to `crdt_update`, may compact, and schedules a text flush. Then `redis_bridge.publish` and
  `_capture_history`.
- `AwarenessMessage`: `_handle_awareness` records the first client id seen in the update on
  `conn.awareness_client_id`, merges into `AwarenessRegistry`, and publishes. There is no `can_write` check:
  viewers appear in presence.

### Fan-out

All delivery, including to clients on the same instance, goes through Redis. `RedisBridge.publish` wraps the
payload in an envelope of instance id, origin connection id and payload. `_reader` polls `get_message` once
a second rather than using `listen()`, and passes `exclude=origin_conn_id` only when the envelope came from
this instance. `_make_forwarder` calls `RoomManager.local_broadcast`, which only enqueues; a full queue is
reported back and closed with 4408 in a spawned task. `_writer` is the only code that writes to the socket.

### Manager lifecycle

`DocumentManager.acquire` retries around a per-document `asyncio.Lock` because eviction can swap the lock
out. `_load` reads `CrdtStore.load` (snapshot merged with the log in id order). If the resulting text is
empty it seeds from `documents.content` via `ContentBridge.load_initial_text`, using `replace_text`, and
writes a snapshot at once.

`release` decrements the refcount. At zero it calls `flush_text_now`, compacts if updates are pending, and
starts `_evict_after_idle`. Eviction drops the entry, the awareness state, the lock and the load counter.

Compaction (`_maybe_compact`, `_compact`) runs inside `handle_update` when `updates_since_snapshot` reaches
`COLLAB_SNAPSHOT_EVERY_UPDATES` or `COLLAB_SNAPSHOT_INTERVAL_SECONDS` have passed. `CrdtStore.snapshot`
writes state, bumps `seq` and deletes log rows up to `last_update_id` in one transaction.

### Flush to `documents.content`

`_do_flush_text` copies the text under the lock, clears `dirty_text`, then calls `ContentBridge.flush_text`
(`set_content_from_collab`, a direct column write that emits no CRDT update) and
`CrdtStore.mark_text_synced`. Callers:

- `release` at refcount zero (forced);
- `flush_open_project_docs`, from the compile route, the agent run route and the zip export route, which calls
  `DocumentManager.flush` for this project's in-memory documents and swallows errors;
- the debounced `_delayed_flush`, `COLLAB_TEXT_FLUSH_DEBOUNCE_MS` after an update. It runs inside `flush_task`, so
  `_do_flush_text` cancels a pending `flush_task` only when it is not the current task.

`flush_open_project_docs` only sees rooms in its own process.

### Disconnect

`_serve`'s `finally` marks the connection closed, cancels the writer and runs `_cleanup`: publish an
awareness offline update if the client was identified, `manager.release`, `rooms.leave`. If the room is now
empty it closes the Redis subscription, drops awareness and calls `history.flush_doc(reason="idle")`, with
exceptions suppressed.

### Shutdown

`_close_collab` in `backend/src/inkstave/app.py` calls `history.flush_all()` first, then
`DocumentManager.aclose()`, which cancels and awaits the flush and eviction tasks.

### Server-side edits

`apply_server_update` (used by restore) acquires the document, runs `replace_text` in one transaction,
appends the update, schedules a flush, releases and returns the raw update. The caller broadcasts it.

### Browser

`InkstaveWsProvider` sends step 1 on every open, answers the server's step 1 with step 2, throttles
awareness, and reconnects with full-jitter backoff. Closes 4401, 4403 and 4404 are terminal: it stops
retrying and goes to `closed`.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Missing or invalid token closes 4401 | `backend/tests/integration/test_collab_ws_api.py::test_missing_token_closes_4401`, `backend/tests/integration/test_collab_ws_api.py::test_invalid_token_closes_4401` |
| An expired token is refused | `backend/tests/integration/test_runtime_ws_auth_reconnect.py::test_expired_token_rejected_4401` |
| A revoked session cannot open a socket (function level, not through the endpoint) | `backend/tests/integration/test_session_revocation.py::test_websocket_and_sse_paths_refuse_a_revoked_session` |
| A non-auth error at admission is not reported as 4401 | `backend/tests/unit/test_collab_ws_auth_logging_92.py::test_ws_non_auth_error_propagates` |
| Non-member closes 4403; unknown project or document closes 4404 | `backend/tests/integration/test_collab_ws_api.py::test_non_member_closes_4403`, `backend/tests/integration/test_collab_ws_api.py::test_unknown_project_closes_4404`, `backend/tests/integration/test_collab_ws_api.py::test_unknown_document_closes_4404` |
| A viewer's update is not applied, persisted or relayed | `backend/tests/integration/test_collab_ws_access.py::test_viewer_update_is_dropped` |
| A viewer still receives others' edits | `backend/tests/integration/test_collab_ws_access.py::test_viewer_receives_editor_updates` |
| Concurrent clients converge, also after an offline period | `backend/tests/integration/test_runtime_collab_convergence.py::test_concurrent_edits_converge`, `backend/tests/integration/test_runtime_collab_convergence.py::test_offline_client_merges_on_reconnect` |
| The relay excludes the originating socket | `backend/tests/integration/test_runtime_collab_convergence.py::test_relay_excludes_origin` |
| Redis delivers across instances and excludes the origin only on its own instance (transport only, no `DocumentManager` involved) | `backend/tests/unit/test_collab_ws_redis.py::test_cross_instance_relay_and_origin_exclusion`, `backend/tests/unit/test_collab_ws_redis.py::test_cross_instance_room_delivery` |
| Concurrent acquires load once | `backend/tests/integration/test_collab_manager.py::test_concurrent_acquire_loads_once`, `backend/tests/integration/test_collab_refactor.py::test_concurrent_acquire_evicted_lock_swap_loads_once` |
| No eviction while a connection holds the document | `backend/tests/integration/test_collab_refactor.py::test_no_eviction_while_connections_remain` |
| Eviction leaves no per-document state | `backend/tests/integration/test_collab_refactor.py::test_locks_and_load_count_bounded_after_eviction` |
| Compaction truncates the log and keeps the text | `backend/tests/integration/test_collab_store.py::test_compaction_truncates_log_and_preserves_text`, `backend/tests/integration/test_collab_refactor.py::test_compaction_boundary_load_is_exact` |
| Appending does not read the log | `backend/tests/integration/test_collab_store.py::test_append_is_constant_cost` |
| The last release persists the final edit | `backend/tests/integration/test_collab_refactor.py::test_flush_on_release_persists_final_edit` |
| A forced flush writes content and emits no CRDT update | `backend/tests/integration/test_collab_manager.py::test_flush_bridges_text_to_spec13`, `backend/tests/integration/test_collab_manager.py::test_bridge_write_does_not_create_crdt_update` |
| The debounced flush writes content while the room stays open | `backend/tests/unit/test_collab_debounced_flush.py::test_the_debounced_flush_writes_the_text_while_the_room_stays_open` |
| An empty CRDT seeds from existing content | `backend/tests/integration/test_collab_manager.py::test_seeds_crdt_from_spec13_content` |
| Text frame or oversize frame closes 4400; oversize update closes 4400 | `backend/tests/integration/test_collab_ws_api.py::test_text_frame_closes_4400`, `backend/tests/integration/test_collab_ws_api.py::test_oversize_frame_closes_4400`, `backend/tests/unit/test_collab_ws_dispatch.py::test_oversize_update_closes_4400` |
| Message flood closes 4429 | `backend/tests/integration/test_collab_ws_api.py::test_rate_limit_closes_4429` |
| A slow consumer is closed 4408 without stalling the others | `backend/tests/unit/test_collab_ws_rooms.py::test_forwarder_closes_slow_consumer_without_stalling_others` |
| Awareness reaches a late joiner and goes offline on disconnect | `backend/tests/integration/test_collab_ws_api.py::test_handshake_sends_awareness_snapshot`, `backend/tests/integration/test_collab_ws_api.py::test_awareness_relay_and_offline` |
| Disconnect tears down the room and subscription | `backend/tests/integration/test_collab_ws_api.py::test_disconnect_tears_down_room`, `backend/tests/integration/test_collab_ws_refactor.py::test_connect_disconnect_cycles_leave_no_leak` |
| Shutdown cancels background tasks | `backend/tests/integration/test_collab_manager.py::test_aclose_cancels_pending_background_tasks` |
| Suggestions survive snapshot, compaction and reload (spec 119) | `backend/tests/integration/test_collab_store.py::test_suggestions_map_survives_compaction` |
| A suggested deletion's text and record are one undo step | `frontend/src/modules/collab/suggestions/suggest-extension.test.ts` (`one undo reverts a suggested deletion`) |
| One undo reverts a suggested insertion and its record together | `frontend/src/modules/collab/suggestions/suggest-extension.test.ts` (`one undo reverts a suggested insertion`) |
| The text always holds the suggested version; the recording rules of spec 119 §5.2 | `frontend/src/modules/collab/suggestions/record.test.ts` |
| Rejecting a deletion restores exactly the removed text; accept and reject are one transaction with origin `review-decision` | `frontend/src/modules/collab/suggestions/review.test.ts` |
| Positions of suggestions follow the text across two peers' concurrent edits | `frontend/src/modules/collab/suggestions/model.test.ts` |
| A deletion of more than 100 000 characters is refused in Suggesting mode only | `frontend/src/modules/collab/suggestions/record.test.ts`, `frontend/src/modules/collab/suggestions/suggest-extension.test.ts` (`a deletion too large to record is refused`) |
| Malformed frames never raise | `backend/tests/unit/test_collab_protocol.py::test_malformed_does_not_raise` |
| Open sockets are closed when access is lost | no dedicated test, and they are not (see Points of attention) |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py`.

| Variable | Default | Effect |
|---|---|---|
| `COLLAB_SNAPSHOT_EVERY_UPDATES` | 200 | Compact after this many updates |
| `COLLAB_SNAPSHOT_INTERVAL_SECONDS` | 30.0 | Or after this long since the last snapshot |
| `COLLAB_TEXT_FLUSH_DEBOUNCE_MS` | 1000 | Delay of the debounced flush |
| `COLLAB_IDLE_EVICT_SECONDS` | 300.0 | Eviction delay after the last release |
| `COLLAB_MAX_UPDATE_BYTES` | 1048576 | Largest single update |
| `COLLAB_WS_MAX_FRAME_BYTES` | 1048576 | Largest inbound frame |
| `COLLAB_WS_SEND_QUEUE_MAX` | 256 | Send queue size per connection |
| `COLLAB_WS_MAX_MSGS_PER_SEC` | 200 | Inbound rate guard per connection (a fixed window, despite the docstring) |
| `COLLAB_REDIS_CHANNEL_PREFIX` | `collab:doc:` | Pub/sub channel prefix |
| `COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS` | 2000 | No effect in production (see below) |
| `COLLAB_WS_PING_INTERVAL_SECONDS` | 25.0 | No effect (see below) |
| `COLLAB_WS_PONG_TIMEOUT_SECONDS` | 10.0 | No effect (see below) |

## Points of attention

**Open sockets are not re-checked.** Authentication and authorization run once, in `_admit`. Nothing in
`backend/src` outside this module touches a room, and `_force_close` has no caller outside
`backend/src/inkstave/modules/collab/ws/messaging.py` and `backend/src/inkstave/modules/collab/ws/connection.py`.
Each case separately:

- Session revoked, or `session_version` bumped, or account deactivated: `is_alive` is consulted only at
  connect. The open socket keeps reading and writing.
- Collaborator removed or leaving: `remove_member` in `backend/src/inkstave/modules/projects/sharing/members.py`
  sets `status = left` and does nothing else. The open socket keeps reading and writing.
- Role changed with `change_role`: `Connection.can_write` is fixed at join. An editor demoted to viewer keeps
  writing; a viewer promoted to editor stays read-only until reconnect.
- Access token expiry: same, the socket outlives the token.
- Project soft-deleted: same. A deleted document cascades its CRDT rows, so the next `append_update` fails on the
  foreign key and `_serve` ends the connection through its generic exception path.

The comment in `frontend/src/modules/collab/InkstaveWsProvider.ts` naming a "removed collaborator (4403)"
applies only to a new connection attempt.

**Rejection close codes do not reach the browser.** 4000, 4401, 4403 and 4404 are sent with
`websocket.close()` before `accept()`. Under uvicorn that is an HTTP 403 on the handshake, reproduced with the
installed uvicorn and `websockets`: "server rejected WebSocket connection: HTTP 403". A browser reports 1006,
so `TERMINAL_CLOSE_CODES` in the provider never matches these and it keeps reconnecting with backoff, up to its
cap, forever. The tests use `backend/tests/collab_ws_harness.py`, which surfaces the ASGI close code directly and
hides this. Only 4400, 4408 and 4429 are sent after accept.

**Multiple instances are not safe for the document state, despite ADR 0029 and the admin guide.** Redis
relays messages to browsers only: `_make_forwarder` calls `local_broadcast` and never applies the update to the
receiving instance's `YDocument`. Reading the code, each instance's copy therefore holds only the updates from its
own clients. `_compact` writes that partial state into `crdt_document_state`, overwriting the other instance's
snapshot, and deletes log rows up to its own `last_update_id`, including rows from the other instance.
`documents.content` also gets a partial text. Awareness snapshots are per instance too. Browsers still converge
with each other, and a reconnect re-sends what the server lacks. This was not reproduced end to end: the
cross-instance tests exercise only `RedisBridge` and `RoomManager`.

**Heartbeat settings are unused.** `COLLAB_WS_PING_INTERVAL_SECONDS` and `COLLAB_WS_PONG_TIMEOUT_SECONDS` are read
into `CollabWsSettings` and nothing reads those fields. The source and `.env.example` say "delegated to the ASGI
server", but `backend/Dockerfile` starts uvicorn with no `--ws-ping-*` flag, so uvicorn's own defaults apply and
these variables change nothing. `CLOSE_DEAD` is never sent for a ping timeout.

**`COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS` is unused in production.** It reaches `RoomManager`, but only
`local_broadcast_timed` reads it, and only tests call that method. `_make_forwarder` uses the non-blocking
`local_broadcast`, so a full queue closes the socket at once. The comment in `build_collab_components` describing a
grace window is wrong.

**Empty text re-seeds.** `_load` seeds whenever `ydoc.text` is empty, not only on first open. A document emptied by
its users and then reopened seeds again from `documents.content`. That is harmless after a clean release, which
writes the empty text first, but not after a crash, given the flush problem above.

**Seeding is invisible to history.** The seed is written to the CRDT snapshot and is not captured. See
[history.md](history.md).

**Each editor connection writes one update.** The browser answers the server's step 1 with step 2 even when it
has nothing to add, and `_handle_update` treats that as an edit: a `crdt_update` row, a relay and a history capture.

**Dead or partial code.** `DocumentManager.flush_text_if_dirty` calls itself and would recurse without end; its
only reference is a `callable` check in `backend/tests/unit/test_keyword_only_signatures_96.py`. `CLOSE_NORMAL` is
unused. `crdt_document_state.text_synced_seq` is written but nothing reads it for recovery.

**Failure in `_join_room`.** It runs before the `try` in `_serve`, so a failed Redis subscribe leaves the refcount
held and the room registered.

**The token is in the URL.** Anything that logs query strings records a live access token. `collab_ws` itself logs
only the two ids.

**Awareness is not validated.** Any member, viewers included, may send an awareness update naming any client id. Only the
first id in the update is recorded for the offline message on disconnect.
