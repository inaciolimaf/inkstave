# ADR 0123 — Several backend replicas: the stored state is the merge point

**Status:** accepted · **Supersedes:** the claim in ADR 0029 that app instances are interchangeable for document state
(its transport part, Redis fan-out with an origin per instance, stands)

## Context

Each backend process keeps its own `pycrdt` copy of every open document. Redis relayed the updates between processes,
but the receiving process only broadcast them to its own sockets and never applied them to its copy. Its copy then
held only its own clients' edits. Compaction wrote that partial state over the snapshot in Postgres and deleted the
log rows up to the process's own high-water mark, which could include rows written by another replica. The text flush
to `documents.content` had the same flaw, and a forced flush before a compile or an agent run only saw the rooms of
its own process.

## Decision

The stored state (snapshot plus log, in Postgres) is the merge point. Every write that depends on the stored state
merges with it first, and the merge runs in one transaction under a per-document Postgres advisory lock
(`pg_advisory_xact_lock(hashtextextended('crdt:<document id>', 0))`), so replicas that share the database serialise on it.

- **Relayed updates are applied.** A replica that receives an update from another replica applies it to its local
  copy with the origin `remote`. It does not append it again (the receiver of the client's update already stored it)
  and does not relay it again, so there is no echo. The text is marked dirty so the flush runs.
- **Compaction merges.** `CrdtStore.snapshot` merges the stored snapshot, every log row it reads and the in-memory
  state, writes the result, and deletes exactly the log rows it read. A stale in-memory copy cannot drop an update
  another replica has stored, and two compactions cannot drop text, because the stored snapshot only grows.
- **Text flush merges.** `CrdtStore.flush_text` writes the text of the merged state into `documents.content` under the
  same lock. Writes are serialised in the order they read the state, so the last write is never older than a
  write that finished before it.
- **Seeding is under the lock.** `CrdtStore.load(seed=True)` seeds an empty document from `documents.content` only
  after it has checked the stored state under the lock, so two replicas opening a document that was never edited cannot
  both seed it (that would double the text).
- **Forced flush needs no round trip.** `flush_open_project_docs` writes every document of the project that has stored
  CRDT state, whether its room is open here or not. The text comes from the stored state, which already holds every
  update a replica has acknowledged, so no Redis request and no wait for acknowledgements is needed, and nothing can hang.

## Alternatives considered

- **A Redis lease per document.** Only the owner compacts and flushes. A forced flush from another replica then needs a
  request, an acknowledgement and a deadline over Redis, and a takeover during a compaction needs fencing. More moving
  parts than the database already provides, and the lease itself can expire under load.
- **Compaction only on the replica that holds the room.** Still loses an update that was stored by another replica and
  is not yet relayed here, unless the owner also merges with the store. It is the merge that makes the design correct.

## Consequences

- Each flush and each compaction reads the snapshot and the log of its document under the lock. The log is bounded by
  `COLLAB_SNAPSHOT_EVERY_UPDATES`, so a read is one snapshot plus a few hundred rows. Flushes are debounced, so this
  is about one read per second for a document being typed in.
- A compaction reloads the stored state into memory afterwards, so a replica that missed a relayed update heals at its
  next compaction or flush.
- A relayed message can be lost (Redis pub/sub is fire-and-forget). The copy then lacks that update until the next
  catch-up, but the stored state has it, so nothing acknowledged is lost.
- A compile, agent run or export flushes every edited document of the project, one short transaction each.
- Not covered here: the history capture buffers in memory per replica (see `docs/system/history.md`), and awareness
  stays per replica.

## Verification

`backend/tests/integration/test_collab_replicas.py` runs two replicas (and a third for the restart case) in one process,
sharing the database and one fake Redis server, with the production forwarder. Each test fails on the code before this
decision: edits converge in both copies, compaction on either replica drops no stored update, a forced flush on one
replica writes the edit typed on the other, and a replica stopping loses no acknowledged edit.
