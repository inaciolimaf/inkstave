# History

Per-document version history. Every edit that reaches the server over the collaboration socket is captured,
coalesced and stored, so a user can list versions, compare two of them, label one and restore one. A restore is
a new edit: nothing is rewritten. It came from specs 36 (capture), 37 (API), 38 (UI) and 40 (refactor). The
module is `backend/src/inkstave/modules/history`.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/history/__init__.py` | Exports `HistoryCaptureService` |
| `backend/src/inkstave/modules/history/models.py` | `HistoryChunk`, `HistoryUpdate`, `HistoryLabel` |
| `backend/src/inkstave/modules/history/schemas.py` | Request and response models |
| `backend/src/inkstave/modules/history/routes.py` | The REST routes |
| `backend/src/inkstave/modules/history/versions/capture.py` | `HistoryCaptureService`: buffer, flush, chunks, replica |
| `backend/src/inkstave/modules/history/versions/reconstruct.py` | `reconstruct_doc`, `reconstruct_state`, `load_current_state`, `current_text`, `text_from_state`, `is_binary` |
| `backend/src/inkstave/modules/history/versions/read.py` | `list_versions`, `list_updates`, `get_diff`, `doc_belongs_to_project` |
| `backend/src/inkstave/modules/history/versions/diff.py` | `diff_text`, `apply_hunks` |
| `backend/src/inkstave/modules/history/versions/labels.py` | Document and project labels |
| `backend/src/inkstave/modules/history/versions/restore.py` | `restore_document`, `restore_project`, `RoomUnreachableError` |
| `backend/src/inkstave/modules/history/versions/jobs.py` | `compact_history`, the ARQ job |
| `backend/src/inkstave/worker.py` | Registers the job and its cron |
| `backend/src/inkstave/modules/collab/ws/components.py` | Builds the capture service |
| `backend/src/inkstave/modules/collab/ws/messaging.py` | `_capture_history` feeds it |
| `frontend/src/modules/history/HistoryPanel.tsx` | Panel in the editor |
| `frontend/src/modules/history/HistoryTimeline.tsx` | Version list |
| `frontend/src/modules/history/HistoryDiffView.tsx` | Diff rendering |
| `frontend/src/modules/history/HistoryLabels.tsx` | Label controls |
| `frontend/src/modules/history/RestoreVersionButton.tsx` | Restore confirmation |
| `frontend/src/modules/history/api.ts` | REST client |
| `frontend/e2e/flows/history.spec.ts` | End-to-end flow |

## Data

Migrations: `backend/migrations/versions/20260610_0900_c3d5f7a91b24_create_history_tables.py` and
`backend/migrations/versions/20260610_1100_d4e6a8b02c35_create_history_labels.py`.
`backend/migrations/versions/20260610_1500_f6a8c2d24e57_history_payload_xor_checks.py` carries the spec 40 note on the XOR
checks; it states no DDL changes.

| Table | Key columns | Constraints |
|---|---|---|
| `history_chunks` | `project_id`, `doc_id`, `start_version`, `end_version`, `base_version`, `base_snapshot` or `base_snapshot_blob_key`, `base_snapshot_size`, `sealed` | `uq_history_chunks_open`: at most one unsealed chunk per document. `ck_history_chunks_base_xor`: exactly one of snapshot and key |
| `history_updates` | `chunk_id`, `project_id`, `doc_id`, `version`, `timestamp`, `author_id`, `payload` or `payload_blob_key`, `payload_size`, `op_count` | `uq_history_updates_doc_version`. `ck_history_updates_payload_xor`. `author_id` is `SET NULL` on user delete |
| `history_labels` | `project_id`, `doc_id` (NULL for project level), `version`, `name`, `created_by`, `created_at`, `payload` | `uq_history_labels_doc_name` and `uq_history_labels_project_name`, partial on `doc_id` |

`doc_id` references `documents.entity_id` with cascade. A project-level label has `version = 0` and a `payload` of
`{doc_id: version}`.

A chunk is a base snapshot plus the ordered updates after it. A version number is per document, starts at 1, and
is the state after that update applies. Payloads and snapshots over `HISTORY_INLINE_MAX_BYTES` live in object
storage under `HISTORY_BLOB_PREFIX` with a random hex name. See [documents.md](documents.md) for the store.

The capture service keeps process memory per document: `_buffers`, `_locks`, `_last_hash`, `_project_ids` and a
replica `YDocument` in `_replicas`.

## Routes

All under `/api/v1/projects/{project_id}`. Errors use the `ErrorEnvelope`; its `type` is the code below.
A non-member gets 404 `project_not_found`; a viewer on a write route gets 403 `insufficient_role`. A `doc_id`
outside the project gets 404 `project_not_found`.

| Method and path | Access | What it does | Errors |
|---|---|---|---|
| GET `/docs/{doc_id}/history/versions` | `PROJECT_READ` | Newest first. `before`, `limit` (default 50, capped at `HISTORY_VERSIONS_PAGE_MAX`). Returns `current_version`, `has_more`, `next_before` | 422 |
| GET `/docs/{doc_id}/history/updates` | `PROJECT_READ` | Ascending, range `from` to `to` | 400 `bad_request` if `from` > `to` |
| GET `/docs/{doc_id}/history/diff` | `PROJECT_READ` | `from` (required), `to` (number or `current`) | 400 `bad_request` on a bad `to`; 404 `history_version_not_found`; 413 with a full `DiffResponse` and `too_large: true` |
| POST `/docs/{doc_id}/history/restore` | `DOC_WRITE` | Body `version`, optional `label_name` | 404 `history_version_not_found`; 409 `duplicate_label`; 409 `room_unreachable` |
| POST `/history/restore` | `DOC_WRITE` | Body `label_id`; restores each document in a project label. 200 with one result per document | 404 `label_not_found` |
| POST `/docs/{doc_id}/history/labels` | `DOC_WRITE` | Body `version`, `name`. 201 | 409 `duplicate_label` |
| GET `/docs/{doc_id}/history/labels` | `PROJECT_READ` | Newest first | |
| DELETE `/docs/{doc_id}/history/labels/{label_id}` | `DOC_WRITE` | 204 | 404 `label_not_found` |
| POST `/history/labels` | `DOC_WRITE` | Body `name`. Records each document's latest version. 201 | 409 `duplicate_label` |
| GET `/history/labels` | `PROJECT_READ` | Project labels, newest first | |
| DELETE `/history/labels/{label_id}` | `DOC_WRITE` | 204 | 404 `label_not_found` |

## How it works

### Capture

The feed is `_capture_history` in `backend/src/inkstave/modules/collab/ws/messaging.py`, called after an update was
applied and published. Viewer updates never get there. Restore also calls `capture_update` directly.

`capture_update` hashes the update in a thread, drops it if it equals the previous hash for this document, and
appends to the buffer, recording the latest author and timestamp. It re-arms a `HISTORY_DEBOUNCE_MS` timer. It does
not touch the database. Reaching `HISTORY_FLUSH_MAX_BUFFER` updates flushes at once with reason `threshold`.

`flush_doc` runs under the document lock. `_take` detaches the buffer and merges it with `merge_updates`, with
`op_count` set to the number of raw updates. `_write` then opens a session and:

1. finds the open chunk;
2. gets the replica, from memory or by `reconstruct_doc` at the open chunk's `end_version`, or an empty `YDocument`
   if no open chunk exists;
3. takes `max(version) + 1`;
4. creates a chunk if there is none, with the replica state as its base;
5. applies the update to the replica and inserts one `HistoryUpdate`;
6. `_roll_over`: at `HISTORY_CHUNK_MAX_UPDATES` versions in the chunk, seals it and opens the next from the replica.

Flush triggers: the idle timer (`idle`), the room becoming empty (`idle`, from `_cleanup`), the buffer threshold
(`threshold`), restore (`manual`), app shutdown (`flush_all`, reason `shutdown`). Reasons `idle` and `shutdown`
then call `_drop_state`, so an idle document costs no memory.

### Reconstruct

`reconstruct_doc` picks the chunk where `base_version <= version <= end_version`, preferring the highest
`base_version`, applies its base, then applies its updates up to `version`. No such chunk raises
`HistoryVersionNotFoundError`. `load_current_state` reads the live state from `crdt_document_state` and
`crdt_update`, not from the history tables.

### Diff

`get_diff` reconstructs both sides. `to=current` uses `current_text`. Either side over `HISTORY_DIFF_MAX_BYTES`
gives `too_large`; the route turns that into a 413. A NUL byte in either side gives `binary: true` with no hunks.
Otherwise `diff_text`, a `difflib.SequenceMatcher` line diff with three lines of context, returns hunks of
`context`, `added` and `removed` segments. Numbers are 1-based.

### Labels

`create_doc_label` checks the name and inserts; `version` is taken as given. `create_project_label` records
`max(version)` for each of the project's documents that has any history, so a document without history is absent
from the payload. `list_versions` joins labels on the versions of the current page.

### Restore

`restore_document` needs `app.state.collab` and a capture service, otherwise 409 `room_unreachable`. In order:

1. `_rewind_room`: reconstruct the target text (404 if absent); `ensure_label_available` (409 before anything
   changes); `DocumentManager.apply_server_update`, whose failure becomes `RoomUnreachableError`.
2. `_record_restore`: `capture_update` with the restoring user as author, `flush_doc(reason="manual")`, then read
   the new maximum version.
3. `_label_restore` attaches the label to the new version.
4. `redis_bridge.publish` broadcasts the update last, with origin `restore-<hex>`, which matches no socket, so
   every client receives it.

`restore_project` loops over the label's payload. A `version < 1` is `skipped`, an exception is `error` with its
message, and it does not roll back documents already restored.

### Compaction

`compact_history` is in the worker's function list and on a cron at every fifth minute, `max_tries=2`. With no
`doc_id` it targets every document with at least `HISTORY_COMPACT_MIN_UPDATES` rows. For each, `_compact_doc`:

1. `_seal_open_tail`: seals an open chunk that reached the threshold and opens the next (safety net for a flush
   that did not seal);
2. `_merge_sealed_chunks`: in sealed chunks only, `_tiny_runs` finds runs of two or more adjacent updates under
   `HISTORY_COMPACT_MERGE_BYTES`; `_merge_run` merges each into its last row, summing `op_count`;
3. `_offload_updates` and `_offload_snapshots`: move oversized inline data to the blob store.

Replaced blobs are deleted after the commit. The job is idempotent.

## Rules and guarantees

| Invariant | Test |
|---|---|
| A first edit creates one chunk and one version | `backend/tests/integration/test_history_capture.py::test_first_edit_creates_chunk_and_update` |
| A burst becomes one row with `op_count` equal to the burst | `backend/tests/integration/test_history_capture.py::test_burst_is_coalesced` |
| Capture does not block on the database | `backend/tests/integration/test_history_capture.py::test_capture_is_non_blocking` |
| An immediately repeated update is ignored | `backend/tests/integration/test_history_capture.py::test_replay_is_deduped` |
| The debounce timer re-arms on each update | `backend/tests/unit/test_history_capture_36.py::test_timer_rearms_on_each_update` |
| The buffer threshold forces a flush | `backend/tests/unit/test_history_capture_36.py::test_threshold_forces_flush` |
| A chunk seals at the threshold, leaving exactly one open | `backend/tests/integration/test_history_capture.py::test_chunk_seals_at_threshold` |
| Versions reconstruct across chunks | `backend/tests/integration/test_history_capture.py::test_reconstruct_across_chunks` |
| An oversized payload goes to the blob store and reads back | `backend/tests/integration/test_history_capture.py::test_oversized_payload_offloads_to_blob` |
| Exactly one of inline and blob key is set | `backend/tests/integration/test_refactor_40.py::test_payload_xor_check_rejects_bad_row` |
| Closing the room flushes the buffer | `backend/tests/integration/test_history_ws.py::test_ws_edit_is_captured_on_room_close` |
| Shutdown flushes buffers | `backend/tests/integration/test_refactor_40.py::test_flush_all_persists_buffered_updates` |
| Restore adds a version and destroys nothing | `backend/tests/integration/test_history_restore.py::test_restore_creates_new_version_non_destructive` |
| A restore label lands on the new version | `backend/tests/integration/test_history_restore.py::test_restore_label_attaches_to_new_version` |
| Room failure leaves no version and no label | `backend/tests/integration/test_history_restore.py::test_restore_atomic_on_room_failure` |
| A duplicate label fails before any change or broadcast | `backend/tests/integration/test_refactor_40.py::test_restore_duplicate_label_fails_fast` |
| Project restore reports per document | `backend/tests/integration/test_history_restore.py::test_project_restore_per_doc_results` |
| Viewers cannot label or restore | `backend/tests/integration/test_history_api_labels.py::test_viewer_cannot_label_or_restore` |
| Non-members get 404 | `backend/tests/integration/test_history_api_labels.py::test_non_member_gets_404` |
| Labels cannot be deleted through another project | `backend/tests/integration/test_history_api_labels.py::test_delete_cross_project_label_404` |
| Label names are unique per document; a label shows in the version list | `backend/tests/integration/test_history_api_labels.py::test_labels_crud_and_duplicate`, `backend/tests/integration/test_history_api_labels.py::test_label_shows_in_versions` |
| Pagination tolerates version gaps | `backend/tests/integration/test_history_api.py::test_versions_pagination_and_gaps` |
| A diff round-trips through `apply_hunks` | `backend/tests/unit/test_history_diff.py::test_apply_diff_reproduces_b` |
| A missing version is 404 in a diff | `backend/tests/integration/test_history_api_diff.py::test_diff_missing_version_404` |
| A binary document returns no hunks | `backend/tests/integration/test_history_api_diff.py::test_diff_binary_document` |
| An oversized diff returns 413 with the full body | `backend/tests/integration/test_history_api_diff.py::test_diff_route_returns_413_with_full_body` |
| Compaction merges, keeps the kept version and is idempotent | `backend/tests/integration/test_history_compact.py::test_compaction_merges_and_is_idempotent` |
| Compaction preserves the head state byte for byte | `backend/tests/integration/test_refactor_40.py::test_compact_preserves_reconstructed_state` |
| Compaction offloads oversized data | `backend/tests/integration/test_history_compact.py::test_compaction_offloads_oversized` |
| History of a document seeded from existing content reconstructs | no dedicated test, and it does not (see Points of attention) |

## Settings

Defined in `backend/src/inkstave/core/config/groups.py`.

| Variable | Default | Effect |
|---|---|---|
| `HISTORY_CAPTURE_ENABLED` | true | Build the capture service. False also makes restore return 409 |
| `HISTORY_DEBOUNCE_MS` | 5000 | Idle time before a flush |
| `HISTORY_FLUSH_MAX_BUFFER` | 200 | Raw updates before a forced flush |
| `HISTORY_CHUNK_MAX_UPDATES` | 100 | Versions per chunk |
| `HISTORY_INLINE_MAX_BYTES` | 65536 | Above this, data goes to the blob store |
| `HISTORY_COMPACT_MIN_UPDATES` | 50 | Rows before the sweep picks a document |
| `HISTORY_COMPACT_MERGE_BYTES` | 4096 | Updates under this may be merged |
| `HISTORY_COMPACT_INTERVAL_S` | 300 | No effect: nothing reads it, the cron in `backend/src/inkstave/worker.py` is fixed |
| `HISTORY_BLOB_PREFIX` | `history/` | Object key prefix |
| `HISTORY_DIFF_MAX_BYTES` | 2097152 | Largest side of a diff |
| `HISTORY_VERSIONS_PAGE_MAX` | 200 | Cap on `limit` |

## Points of attention

**A document with content before its first edit has broken history.** `DocumentManager._load` seeds the CRDT from
`documents.content`, and that seed is never captured. `_replica` starts from an empty `YDocument` when no chunk
exists, so the first chunk has an empty base. Client updates reference items of the seed, and replaying them on the
empty base leaves them pending. Reproduced directly: live text `hello BIG world seeded`, replay on an empty base
`''`. By reading, then, `diff` shows wrong text for such documents and a restore replaces the live document with that
wrong text, as a new version. This covers every document that had content when first opened, including imported
projects and the starter project. Test fixtures start from an empty document, so nothing catches it.

**Merged-away versions do not 404.** After compaction an intermediate version number has no row, but its chunk still
spans it, so `reconstruct_doc` silently returns the state of the previous kept row. A diff or a restore of such a
number gives older text than the user saw. `create_doc_label` does not check that `version` exists, and a label
on a merged-away version no longer appears in `list_versions`, though `list_doc_labels` still returns it. The chunk's
version range is not changed by compaction. No test covers intermediate versions.

**A failed flush loses the buffer.** `_take` removes the buffer before `_write` runs. If `_write` raises, those
updates are gone, and the replica may already include them. The comment in `_on_timer` says a failed flush is retried
by the next edit or the compaction job; neither has the data. `_cleanup` also suppresses the error. The live document
is unaffected, only its history.

**Coalescing loses authorship.** A row keeps the last author of its buffer, so two users typing within one debounce
window appear as one. `author_id` becomes NULL on user delete, shown as unknown. Restore's `flush_doc` can absorb
other users' buffered edits into the row attributed to the restorer.

**One history stream per process.** Version numbers come from `max(version) + 1` in a session, and the buffer and
replica are per instance. Two instances flushing the same document can hit `uq_history_updates_doc_version`, which
loses the buffer as above. Restore mutates only the local `DocumentManager`. See also the multi-instance
note in [collab.md](collab.md).

**No-op versions.** The empty step 2 an editor sends on connect is captured like any update, so opening a document
can add a version with no change. Dedupe only compares with the immediately previous update.

**Offloaded blobs are not removed with their rows.** Chunks and updates cascade when a document or project goes, and
nothing outside `backend/src/inkstave/modules/history` refers to the blob keys, so those objects stay. Compaction
deletes only what it replaced. A blob written before a failed commit also stays.

**Compaction scope.** The sweep has no marker of what it finished, so every document over the threshold has its sealed
chunks re-read every five minutes, forever, inside one transaction across all documents.

**Diff cost.** The size guard runs after both sides are reconstructed, so a large document is fully rebuilt in the
request before the 413. Nothing rejects `from` greater than `to`; the diff simply runs backwards. `/updates` does
reject it.

**Label scopes.** Document and project labels are unique in separate scopes, so a project label can share a document
label's name.

**Project restore on a poisoned session.** `restore_project` shares one session across documents and catches every
exception, so a database error on one document may fail the following ones with a less useful message.

**`ensure_snapshot`** is public and has no caller. The docstring leaves it for spec 37, which did not use it.

**Project label scope.** `create_project_label` stores only documents with history, so a document created later, or
never edited, is untouched by a project restore.
