# Spec 36 — History Capture from the CRDT Stream (requirements)

## 1. Summary

This spec adds a server-side history capture layer that observes the CRDT update
stream produced by spec 28 and records a compact, restorable version history for
every document. It periodically takes full snapshots, accumulates incremental
updates between snapshots, debounces writes so live typing is not slowed, and
runs a compaction pass as an ARQ job. Large payloads are offloaded to blob
storage (spec 14). This spec delivers **only capture + storage**; the read API
(spec 37) and UI (spec 38) build on top of it.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 28** — pycrdt document model, the Yjs binary update protocol, and the
    persistence hook where server-applied updates are observed. This is the
    single source of history events.
  - **Spec 13** — document content storage & CRUD; provides `documents` (doc_id,
    project_id) that history rows reference.
  - **Spec 14** — binary file / blob storage abstraction (disk or S3-compatible);
    used to offload oversized history payloads out of Postgres.
- **Unlocks:**
  - **Spec 37** — history API reads `history_chunks` / `history_updates` and the
    snapshot blobs this spec writes.
  - **Spec 38** — history UI consumes spec 37.
- **Affected areas:** backend (CRDT persistence hook, history service, ARQ job),
  database (two new tables + migration), infra (blob storage usage), docs (ADR).

## 3. Goals

- Observe every server-applied CRDT update for a document and append it to an
  ordered, durable history without blocking the WebSocket/persistence path.
- Take a **full state snapshot** of a document's CRDT state at controlled points
  (first edit, on idle/flush, and after a configurable number of updates).
- Store history as **chunks**: a chunk = one snapshot + the ordered incremental
  updates that follow it, so any version is reconstructible by replaying updates
  onto the chunk's base snapshot.
- Debounce/coalesce captures so that a burst of keystrokes produces a small
  number of rows, not one row per keystroke.
- Run **compaction** as an ARQ job: merge tiny updates, seal full chunks, and
  move large payloads to blob storage; never lose the ability to restore.
- Keep tests fast: the capture path is unit/integration tested with in-memory or
  test-DB fakes; the compaction job is invoked directly in tests and is otherwise
  triggered by a schedule that is mocked.

## 4. Non-goals (explicitly out of scope)

- The HTTP API to list versions, compute diffs, restore, or manage labels — **spec 37**.
- Any frontend/history UI — **spec 38**.
- Project-wide (multi-file) history *views* — capture is per-document here; spec 37
  aggregates across a project for listing. We still record `project_id` on rows so
  37 can aggregate without a migration.
- Notifications/email — **spec 39**.
- Deleting/pruning history for storage-quota reasons (a later hardening concern);
  compaction here only *compacts*, it does not destroy restorable state.

## 5. Detailed requirements

### 5.1 Data model

Two tables, plus optional blob offload. All timestamps are `timestamptz` (UTC).
Add one Alembic migration creating both tables and their indexes.

#### 5.1.1 `history_chunks`

A chunk groups a base snapshot with the updates captured after it.

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `project_id` | `uuid` | NOT NULL, FK → `projects.id` ON DELETE CASCADE |
| `doc_id` | `uuid` | NOT NULL, FK → `documents.id` ON DELETE CASCADE |
| `start_version` | `bigint` | NOT NULL — version of the first update in this chunk (== `base_version + 1` for non-empty chunks; equals `base_version` for an empty freshly-opened chunk) |
| `end_version` | `bigint` | NOT NULL — version of the last update captured in this chunk so far |
| `base_version` | `bigint` | NOT NULL — version the `base_snapshot` represents |
| `base_snapshot` | `bytea` | NULLABLE — full Yjs state (`Y.encodeStateAsUpdate`) for `base_version`; NULL when offloaded to blob storage (see `base_snapshot_blob_key`) |
| `base_snapshot_blob_key` | `text` | NULLABLE — blob storage key when the snapshot was offloaded; exactly one of `base_snapshot` / `base_snapshot_blob_key` is non-NULL |
| `base_snapshot_size` | `integer` | NOT NULL — byte length of the base snapshot (regardless of storage location) |
| `sealed` | `boolean` | NOT NULL default `false` — a sealed chunk receives no more updates; the open (un-sealed) chunk is the current tail |
| `created_at` | `timestamptz` | NOT NULL default `now()` |
| `updated_at` | `timestamptz` | NOT NULL default `now()` |

Indexes / constraints:
- Index `ix_history_chunks_doc_version` on `(doc_id, start_version)`.
- Index `ix_history_chunks_project` on `(project_id, created_at)`.
- **Partial unique** index `uq_history_chunks_open` on `(doc_id)` `WHERE sealed = false`
  — guarantees at most one open chunk per document.

#### 5.1.2 `history_updates`

One row per captured incremental update (already debounced/coalesced — see §5.4).

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | `uuid` | PK, default `gen_random_uuid()` |
| `chunk_id` | `uuid` | NOT NULL, FK → `history_chunks.id` ON DELETE CASCADE |
| `project_id` | `uuid` | NOT NULL, FK → `projects.id` ON DELETE CASCADE (denormalised for spec-37 aggregation) |
| `doc_id` | `uuid` | NOT NULL, FK → `documents.id` ON DELETE CASCADE |
| `version` | `bigint` | NOT NULL — monotonic per `doc_id`; the version *after* this update is applied |
| `timestamp` | `timestamptz` | NOT NULL — wall-clock time the update was captured |
| `author_id` | `uuid` | NULLABLE, FK → `users.id` ON DELETE SET NULL — the user who originated the update (NULL for system/agent/unknown) |
| `payload` | `bytea` | NULLABLE — the Yjs binary update (`Y.encodeStateAsUpdate` of the diff / merged updates); NULL when offloaded |
| `payload_blob_key` | `text` | NULLABLE — blob key when offloaded; exactly one of `payload` / `payload_blob_key` is non-NULL |
| `payload_size` | `integer` | NOT NULL — byte length of the update |
| `op_count` | `integer` | NOT NULL default `1` — how many raw CRDT updates were coalesced into this row (for metrics/compaction) |

Indexes / constraints:
- **Unique** `uq_history_updates_doc_version` on `(doc_id, version)`.
- Index `ix_history_updates_chunk` on `(chunk_id, version)`.
- Index `ix_history_updates_project_ts` on `(project_id, timestamp)`.

> `version` is the document's history version counter, distinct from any Yjs
> internal clock. It is a `bigint` that increments by 1 per captured `history_updates`
> row. Maintain it in the history service (next version = current max for doc + 1),
> guarded by the per-doc capture lock (§5.4).

#### 5.1.3 Storage location rule (invariant)

For both `base_snapshot` and `payload`: **exactly one** of the inline `bytea` column
and the `*_blob_key` column is non-NULL. A payload is stored inline when its size
≤ `HISTORY_INLINE_MAX_BYTES`; otherwise it is written to blob storage (spec 14) and
only the key is kept. The `*_size` column always records the true size.

### 5.2 Backend / service contracts

Create a `HistoryCaptureService` (module `backend/app/history/capture.py` or the
established layout). It exposes:

```python
async def capture_update(
    *, project_id: UUID, doc_id: UUID,
    update: bytes,                 # raw Yjs binary update just applied server-side
    author_id: UUID | None,
    at: datetime,                  # capture time (UTC)
) -> None: ...
```

Contract:
- Called from the spec-28 CRDT persistence hook **after** an update is successfully
  applied to the authoritative server document. Must be non-blocking with respect
  to the live sync path (see §5.4 — it enqueues into a per-doc debounced buffer and
  returns immediately; the actual DB write happens on flush).
- Must be idempotent-safe: the same raw update applied twice (e.g. reconnect replay)
  must not create duplicate captured versions. De-dupe by hashing the raw update and
  skipping if the identical hash was the immediately-preceding raw update for the doc
  within the current debounce window.

```python
async def flush_doc(*, doc_id: UUID, reason: Literal["idle", "shutdown", "threshold", "manual"]) -> None: ...
```

Contract:
- Coalesces the buffered raw updates for `doc_id` into a single merged Yjs update
  (`Y.mergeUpdates` equivalent via pycrdt), allocates the next `version`, and writes
  **one** `history_updates` row into the document's open chunk. Updates the chunk's
  `end_version` and `updated_at`.
- If there is no open chunk for the doc, it first creates one (see snapshot logic).
- Offloads payloads larger than `HISTORY_INLINE_MAX_BYTES` to blob storage.
- A flush with an empty buffer is a no-op.

```python
async def ensure_snapshot(*, project_id: UUID, doc_id: UUID, current_state: bytes, version: int) -> None: ...
```

Contract:
- Called to seal the open chunk and start a new one with a fresh base snapshot when
  the open chunk has accumulated ≥ `HISTORY_CHUNK_MAX_UPDATES` updates (checked on
  flush). Marks the old chunk `sealed = true`, writes a new `history_chunks` row whose
  `base_snapshot` is `current_state` at `version`.
- The **very first** capture for a doc also creates the initial chunk with a base
  snapshot of the document's state *before* that first update (so version history
  has a true starting point). If the doc already had content from spec 13, the base
  snapshot is the doc's current CRDT state at the moment history capture begins.

#### 5.2.1 Version reconstruction helper (internal, used by spec 37)

Provide `async def reconstruct_state(*, doc_id: UUID, version: int) -> bytes` that:
- Finds the chunk whose `[base_version, end_version]` range contains `version`.
- Loads its base snapshot (inline or from blob).
- Replays, in `version` order, every `history_updates` payload in that chunk up to and
  including the target `version`, merging onto the base via pycrdt.
- Returns the resulting full Yjs state. This is the primitive spec 37's diff/restore
  use. It must be exported but spec 36 only needs it for its own tests.

### 5.3 Frontend / UI

None. (History UI is spec 38.)

### 5.4 Real-time / jobs / capture trigger

#### 5.4.1 Capture trigger (debounced)

- Maintain an in-process **per-doc debounce buffer**: a dict keyed by `doc_id`
  holding the list of raw updates, the latest author, first/last timestamps, and an
  asyncio timer/handle. Guard each doc's buffer with a per-doc `asyncio.Lock`.
- On `capture_update`, append the raw update to the doc's buffer and (re)arm a debounce
  timer of `HISTORY_DEBOUNCE_MS` (default 5000 ms). When the timer fires, call
  `flush_doc(reason="idle")`.
- Force an immediate flush when the buffer reaches `HISTORY_FLUSH_MAX_BUFFER` raw
  updates (default 200) without waiting for idle — call `flush_doc(reason="threshold")`.
- On the spec-28 "document flushed to persistence" / room-empty event, call
  `flush_doc(reason="idle")` for that doc so closing a doc never loses buffered history.
- On graceful shutdown, flush all non-empty buffers (`reason="shutdown"`).
- The buffer is process-local. With multiple app workers, each worker buffers updates
  for the docs whose CRDT rooms it hosts; since spec 28/29 pins a doc's authoritative
  room to a single worker, no cross-worker coordination is required. If that assumption
  does not hold in the implemented spec 28, fall back to flushing on every persistence
  write (document this in the ADR).

#### 5.4.2 Compaction ARQ job

Define an ARQ job `compact_history` in the backend worker:

```python
async def compact_history(ctx, doc_id: str | None = None) -> dict: ...
```

- When `doc_id` is given, compact that document; when `None`, iterate documents that
  have an open chunk with `op_count`-weighted update count above
  `HISTORY_COMPACT_MIN_UPDATES` (default 50) or with un-offloaded oversized payloads.
- Compaction steps per doc:
  1. **Merge tiny updates:** within a sealed chunk, merge runs of adjacent
     `history_updates` smaller than `HISTORY_COMPACT_MERGE_BYTES` into a single merged
     payload, preserving the *latest* `version`, summing `op_count`, and keeping the
     latest `timestamp` and `author_id`. Replaying the merged result must reproduce the
     same final state (verified in tests via `reconstruct_state`). Delete the merged-away
     rows in the same transaction.
  2. **Seal the tail** if the open chunk exceeds `HISTORY_CHUNK_MAX_UPDATES` and was not
     already sealed by `ensure_snapshot`.
  3. **Offload** any inline payload/snapshot whose size > `HISTORY_INLINE_MAX_BYTES` to
     blob storage and NULL the inline column.
- The job must be **safe to re-run** (idempotent) and must never reduce the set of
  reconstructible versions for any version that already existed before compaction,
  **except** that intermediate (merged-away) versions cease to be individually
  addressable — merging is only permitted *within already-sealed history and only
  across adjacent versions captured close in time*, and the merged row keeps the
  highest version of the run. Document this trade-off in the ADR; spec 37's listing
  must tolerate gaps in the version sequence.
- **Scheduling:** the job is enqueued by a lightweight scheduler (ARQ cron or a periodic
  enqueue) every `HISTORY_COMPACT_INTERVAL_S` (default 300). In tests, the scheduler is
  **mocked** — tests call `compact_history(ctx, doc_id=...)` directly.

### 5.5 Configuration

Add to `.env.example` (with the documented defaults):

| Env var | Default | Meaning |
| --- | --- | --- |
| `HISTORY_DEBOUNCE_MS` | `5000` | Idle debounce window before flushing buffered updates |
| `HISTORY_FLUSH_MAX_BUFFER` | `200` | Raw updates buffered before a forced flush |
| `HISTORY_CHUNK_MAX_UPDATES` | `100` | Captured updates per chunk before sealing + new snapshot |
| `HISTORY_INLINE_MAX_BYTES` | `65536` | Payloads/snapshots above this size are offloaded to blob storage |
| `HISTORY_COMPACT_MIN_UPDATES` | `50` | Min updates in a doc before the sweep compacts it |
| `HISTORY_COMPACT_MERGE_BYTES` | `4096` | Adjacent updates smaller than this may be merged during compaction |
| `HISTORY_COMPACT_INTERVAL_S` | `300` | Scheduler interval for the compaction sweep (mocked in tests) |
| `HISTORY_BLOB_PREFIX` | `history/` | Key prefix used in blob storage (spec 14) for offloaded history payloads |

All read through the Pydantic settings object established in spec 02.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave derives history
> from the **CRDT update stream**, not from OT/sharejs ops — so treat these as
> approach-only references and write your own implementation.

- `services/project-history/app/js/UpdatesProcessor.js` — how Overleaf batches and
  processes raw updates into history; learn the batching/flush idea.
- `services/project-history/app/js/UpdateCompressor.js` and `OperationsCompressor.js`
  — how adjacent updates are compressed/merged; informs §5.4.2 compaction (write your own).
- `services/project-history/app/js/SnapshotManager.js` — snapshot reconstruction from a
  base + ops; informs §5.2.1 `reconstruct_state`.
- `services/history-v1/storage/lib/chunk_store/` (`postgres.js`, `index.js`) — the
  chunk-as-(snapshot + changes) storage model; informs §5.1 table shapes.
- `services/history-v1/storage/lib/blob_store/` and `batch_blob_store.js` — offloading
  large payloads to a blob store keyed by content; informs §5.1.3 offload rule.
- `services/project-history/app/js/FlushManager.js` — idle/threshold flush triggers;
  informs §5.4.1.

## 7. Acceptance criteria

1. **Given** a fresh document with no history, **when** a user makes an edit that
   produces a CRDT update and `HISTORY_DEBOUNCE_MS` elapses, **then** exactly one
   `history_chunks` row (open, with a base snapshot) and exactly one `history_updates`
   row (version 1) exist for that doc.
2. **Given** a burst of N (> 1) raw updates within the debounce window, **when** the
   window elapses, **then** they are coalesced into **one** `history_updates` row whose
   `op_count == N` and whose merged payload, replayed on the base snapshot, reproduces
   the document's current state.
3. **Given** the open chunk has reached `HISTORY_CHUNK_MAX_UPDATES` captured updates,
   **when** the next flush occurs, **then** the chunk is marked `sealed = true`, a new
   open chunk is created with a fresh base snapshot, and the partial-unique index still
   permits exactly one open chunk for the doc.
4. **Given** a captured payload larger than `HISTORY_INLINE_MAX_BYTES`, **when** it is
   stored, **then** its inline `payload`/`base_snapshot` column is NULL, its `*_blob_key`
   references a blob in storage under `HISTORY_BLOB_PREFIX`, and `*_size` records the
   true byte length.
5. **Given** a document with several chunks and updates, **when** `reconstruct_state`
   is called for any captured `version`, **then** it returns the full Yjs state equal
   to applying all updates up to that version onto the appropriate base snapshot.
6. **Given** the same raw update is delivered twice in succession (replay), **when**
   captured, **then** no duplicate `history_updates` version is created.
7. **Given** a document with mergeable adjacent tiny updates in a sealed chunk,
   **when** `compact_history` runs, **then** those rows are merged (fewer rows,
   summed `op_count`), the final reconstructed state is unchanged, and running the job
   a second time produces no further change (idempotent).
8. **Given** the live CRDT sync path, **when** `capture_update` is called, **then** it
   returns without performing a synchronous DB write (the write happens on debounced
   flush) — verified by asserting no DB row appears until the timer/threshold fires.
9. **Given** a doc whose room empties (spec-28 persistence/flush event), **when** that
   event fires with buffered updates pending, **then** a flush occurs and the buffered
   updates are persisted (no history loss on close).
10. **Given** the Alembic migration is applied then downgraded, **then** both tables and
    all indexes (including the partial-unique open-chunk index) are created and cleanly
    dropped.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes. The
> compaction scheduler is mocked; only the job body is invoked directly. No real
> WebSocket or LaTeX work here.

- **Unit (pytest):**
  - Debounce buffer: appending raw updates re-arms the timer; threshold forces flush;
    empty flush is a no-op (use a fake/loop-controlled clock or call flush directly).
  - Coalescing: merging N raw Yjs updates via pycrdt yields a payload that reconstructs
    the expected state (criterion 2).
  - Offload decision: size threshold routes to inline vs. blob key (mock the spec-14
    blob store) (criterion 4).
  - De-dupe by hash (criterion 6).
  - `reconstruct_state` across single-chunk and multi-chunk cases (criterion 5).
- **Integration (pytest + test Postgres + fake Redis):**
  - End-to-end capture using a real pycrdt doc and the real `HistoryCaptureService`
    against the test DB: first edit creates chunk+update (criterion 1); chunk sealing at
    threshold (criterion 3); room-empty flush (criterion 9).
  - `compact_history` job against the test DB: merge + idempotency (criterion 7);
    offload of oversized rows (criterion 4) using the spec-14 storage configured for
    local disk in tests.
  - Alembic upgrade/downgrade round-trip (criterion 10).
- **E2E (Playwright):** none at this stage (no UI yet).
- **Performance/budget note:** Tests construct CRDT updates in-memory and call the
  service/job directly; the debounce timer is bypassed (flush called explicitly) so no
  test waits on real wall-clock delays. The periodic scheduler is never started in tests.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; ADR for chunking/debounce/merge
      trade-offs added under `docs/`.
- [ ] No Overleaf code copied.
