# ADR 0028 — Server-side CRDT: snapshot/compaction & the CRDT↔REST bridge

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 28 — Server-side CRDT document model (pycrdt)

## Context

Inkstave needs a server-held CRDT for each document so real-time collaboration
(spec 29 transport, spec 31 browser binding) and history (spec 36/37) have a
durable, mergeable substrate — while REST readers and the Tectonic compiler keep
seeing the canonical plain text (spec 13). This is a **library** (no transport).

> **Originality.** Overleaf uses Operational Transformation (ShareJS). Inkstave
> uses a **CRDT** (Yjs/Yrs via `pycrdt`). Overleaf's document-updater was read
> only for the operational lifecycle (load → mutate → flush → evict); the merge
> algorithm and persistence are an independent design.

## Decisions

### 1. Persistence: snapshot + append-only log, with compaction

Two tables (`crdt_document_state` 1:1 with a `documents` row by entity id, and an
append-only `crdt_update` log):

- **Append is O(1)** — `handle_update` does a single INSERT into `crdt_update`,
  never reading the existing log (the hot path).
- **Load is snapshot-first, then ordered log** — `load` reads the snapshot
  `state` and every `crdt_update` in `id` order and `merge_updates`-es them into
  one full state. CRDT merge is order-tolerant, but we replay in id order for
  determinism.
- **Compaction** — after `COLLAB_SNAPSHOT_EVERY_UPDATES` (200) updates or
  `COLLAB_SNAPSHOT_INTERVAL_SECONDS` (30 s), `snapshot()` writes the current full
  state + state vector, bumps `seq`, and **deletes** `crdt_update` rows with
  `id <= high-water-mark` in one transaction. The manager serializes a doc's
  appends and compaction under a per-document lock and passes the last appended
  id as the high-water mark, so compaction never deletes an update not yet in the
  snapshotted state.

Persistence and compaction run **inline** in the manager (binary updates are
small; compaction is one quick transaction) — no ARQ job, per the spec.

### 2. The CRDT↔REST bridge (no feedback loop)

`ContentBridge` keeps `documents.content` in sync with the live CRDT text:

- **Seed on first open:** if the CRDT state is empty but spec-13 content is
  non-empty, `replace_text` seeds the CRDT and the seeded state is snapshotted.
- **Flush CRDT → content:** debounced (`COLLAB_TEXT_FLUSH_DEBOUNCE_MS`, 1000 ms)
  and forced on `release`/`flush`. Writes go through a narrow
  `set_content_from_collab` seam that updates the `content` column **directly**
  (no version check, bumps `version` only on a real change so REST optimistic
  concurrency still works) — it never touches the `YDocument`, so **a flush never
  re-emits a CRDT update** (no loop). The write is idempotent (a no-op when the
  text is unchanged).

### 3. State vectors compare logically, not by bytes

A Yjs state vector's byte encoding lists clients in *learning order*, so two
converged docs can hold byte-different but logically-identical state vectors. The
convergence test decodes to `{client_id: clock}` and compares those — the correct
reading of "identical state vectors" (criterion 2). Production code never
compares state-vector bytes.

### 4. Manager lifecycle & awareness

`DocumentManager` owns in-memory `YDocument`s with **refcounting** and a
per-document lock guaranteeing a **single in-flight load** under concurrent
`acquire`s. When refcount hits 0 it flushes + snapshots and, after
`COLLAB_IDLE_EVICT_SECONDS` (300 s), evicts the doc to bound memory. Updates over
`COLLAB_MAX_UPDATE_BYTES` (1 MiB) raise `UpdateTooLarge`.

**Awareness is ephemeral** — `AwarenessRegistry` (in memory, backed by pycrdt's
`Awareness`) merges/relays update blobs, snapshots full state for new joiners,
and emits an offline marker on `remove_client`. Nothing is persisted.

### 5. Protocol

`protocol.py` implements the standard **y-protocols** framing (MESSAGE_SYNC with
SYNC_STEP_1/2/UPDATE, MESSAGE_AWARENESS) reusing pycrdt's var-uint/var-bytes
encoders, decoding to a typed union; unknown/malformed input → `UnknownMessage`
(never raises). Spec 29 wraps the manager's raw relay bytes for broadcast.

## Consequences

- New module `backend/src/inkstave/collab/` (protocol, ydocument, store,
  awareness, content_bridge, manager); new tables via Alembic
  `b7c4e9d21f08`; new dep `pycrdt`.
- New `COLLAB_*` settings in `.env.example`.
- Pure CRDT logic is unit-tested; persistence + manager use the transactional
  test DB. No transport, no network — the suite stays well under 2 minutes.
- Spec 29 drives this manager over a JWT WebSocket; spec 31/32 consume the same
  protocol; spec 36/37 consume the persisted update log.
