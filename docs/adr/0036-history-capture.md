# ADR 0036 — History capture from the CRDT stream: chunking, debounce, merge

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 36 — History Capture from the CRDT Stream

## Context

Inkstave derives version history from the **server-applied CRDT (Yjs/pycrdt)
update stream** (spec 28), not from OT ops. This spec records a compact,
restorable per-document history without slowing live editing, leaving the read
API (spec 37) and UI (spec 38) to build on top.

## Decisions

### 1. Chunk model + reconstruction

History is stored as **chunks**: `history_chunks` (a base snapshot at
`base_version`) + `history_updates` (ordered incremental updates after it). Any
version `v` is rebuilt by `reconstruct_state` = load the chunk whose
`[base_version, end_version]` contains `v`, apply its base, then replay the
chunk's update payloads with `base_version < version ≤ v` (pycrdt `apply_update`).
A partial-unique index `uq_history_chunks_open (doc_id) WHERE sealed = false`
guarantees **at most one open chunk per document**.

### 2. Capture is debounced + coalesced (live path never blocks)

`capture_update` only appends the raw update to an in-process per-doc buffer and
(re)arms a timer — **no DB write**. The write happens on `flush_doc`, which merges
the buffered raw updates (`pycrdt.merge_updates`) into **one** `history_updates`
row with `op_count = N`. Flush triggers: idle debounce (`HISTORY_DEBOUNCE_MS`,
5 s), a forced flush at `HISTORY_FLUSH_MAX_BUFFER` (200) raw updates, **room-empty**
(wired into the spec-29 `_cleanup` so closing a doc never loses buffered history),
and graceful shutdown (`flush_all`). Each buffer is guarded by a per-doc
`asyncio.Lock`. **De-dupe:** an immediately-repeated identical raw update (reconnect
replay) is skipped by SHA-256 hash, so no duplicate version is created.

### 3. Snapshot bases come from a per-doc replica (no extra CRDT reads)

The service keeps a per-doc replica `Y.Doc`, built from the captured stream itself
(rebuilt from history on demand after a restart). The **very first chunk** has an
*empty* base (`base_version = 0`); its first update (version 1) carries the merged
first batch — for a document edited from empty (the common, fully-collaborative
case) this reproduces the full content. On chunk seal the new chunk's base is the
replica's current full state. **Known assumption:** capture treats a document's
CRDT history as beginning empty; a document whose content pre-existed history
capture via spec-13 REST (before any collaborative edit) would have that content
reconstructed only from the captured stream — acceptable because Inkstave
documents are created empty in the CRDT and content arrives as updates. The replica
is dropped on idle/shutdown flush to bound memory.

### 4. Wiring point

Capture is driven from the spec-29 WS `_dispatch` **after** `manager.handle_update`
succeeds (the server-apply boundary), tagged with the connection's `user_id` (as
`author_id`) and `project_id`. **Remote (Redis-relayed) updates are not captured**
— the originating instance already captured them (no double-capture; spec 28 pins a
doc's authoritative room to one worker). It is gated by `HISTORY_CAPTURE_ENABLED`.

### 5. Storage-location invariant + offload

For both `base_snapshot` and `payload`: **exactly one** of the inline `bytea`
column and the `*_blob_key` column is non-NULL. Payloads/snapshots larger than
`HISTORY_INLINE_MAX_BYTES` (64 KiB) are written to blob storage (spec 14) under
`HISTORY_BLOB_PREFIX`; `*_size` always records the true byte length.

### 6. Compaction (ARQ job, idempotent)

`compact_history(ctx, doc_id=None)` runs on a ~5-minute cron (mocked in tests):
within **sealed** chunks it merges *maximal runs* of adjacent updates smaller than
`HISTORY_COMPACT_MERGE_BYTES` into one row (keeping the **highest** version, summed
`op_count`, latest timestamp/author), then offloads any oversized inline payload or
snapshot. **Trade-off:** merged-away intermediate versions cease to be individually
addressable (the run's highest version is retained and the final reconstructed
state is identical) — spec 37's listing must tolerate gaps in the version sequence.
Maximal merging makes the job a fixpoint, so re-running is a no-op (verified).

## Consequences

- Two tables + migration `c3d5f7a91b24` (model↔migration drift checked by the
  existing autogenerate test). New `history/` package (`capture.py`, `jobs.py`),
  `HistoryCaptureService` on `CollabComponents`, and a `compact_history` job + cron
  in the worker. 8 new `HISTORY_*` settings (documented in `.env.example`).
- `reconstruct_state` is exported as the primitive spec 37's diff/restore will use.
- Tests construct CRDT updates in memory and call the service/job directly (the
  debounce timer is bypassed); the periodic scheduler is never started in tests, so
  no test waits on wall-clock delays.
