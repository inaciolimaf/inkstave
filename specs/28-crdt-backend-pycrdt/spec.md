# Spec 28 — Server-side CRDT document model (pycrdt) (requirements)

## 1. Summary

This spec gives Inkstave a **server-side CRDT document model** using `pycrdt`
(Python bindings to the Yrs/Yjs CRDT). Each Inkstave document (spec 13) is
represented as a Yjs document containing one shared **text** type. The server can
apply incoming binary **Yjs updates**, produce updates and **state vectors** for
the Yjs **sync protocol** (sync step 1/2), track **awareness** state, persist the
CRDT state durably to PostgreSQL (state-vector + update-log snapshotting), and
**bridge** the CRDT text back to the spec-13 plain-text content so REST readers
and the Tectonic compiler always see the current text. This spec is a **library
only** — no HTTP or WebSocket (those are spec 29).

> **Originality note.** Overleaf uses Operational Transformation (ShareJS), *not*
> CRDT. Its `document-updater` is referenced only for the *operational concerns*
> of holding live document state and flushing it to a database — never for the
> merge algorithm. Inkstave's CRDT model, sync protocol handling, and persistence
> are an independent design.

## 2. Context & dependencies

- **Depends on:** **spec 13** (document content API/storage) — provides the
  document entity, its canonical `content` (text) column, the project/file-tree
  association, and the existing read/write paths the compiler and REST clients
  use. This spec keeps that canonical text in sync with the CRDT.
- **Unlocks:**
  - **spec 29** (collab WebSocket) — transports the protocol messages this spec
    defines and drives the document manager.
  - **spec 31/32** (frontend binding, presence) — consume the same protocol.
  - **spec 36/37** (history) — the persisted update log is the substrate for
    snapshots/diffs.
- **Affected areas:** backend (`backend/app/collab/` library + Alembic
  migration), docs (ADR). No frontend.

## 3. Goals

- Define `YDocument`: a wrapper over a `pycrdt.Doc` holding a single shared text
  (`pycrdt.Text`, root key `"content"`) with helpers to read/replace text and to
  apply/produce updates.
- Implement the **Yjs sync protocol** message handling server-side:
  - **Sync Step 1** (a client's state vector) → server replies with a **Sync
    Step 2** update (the diff the client is missing) **and** its own Step 1.
  - **Sync Step 2 / Update** (a client's update) → server applies it and emits the
    resulting update for relay.
  - **Awareness** updates → server tracks per-client awareness and relays them.
- Implement **persistence**: durably store the CRDT state in Postgres as a
  compact **snapshot** (full Yjs update encoding the document state) plus an
  **append-only update log**, with periodic compaction (snapshot + truncate log).
- Implement the **REST/compiler bridge**: whenever the CRDT text changes (and on
  flush), write the current text back into the spec-13 `content` so existing REST
  reads and the compiler see live content; and **load** initial CRDT state from
  the spec-13 content the first time a document is opened.
- Provide a **DocumentManager** that owns the in-memory `YDocument` instances
  (one per open document), lazily loads/persists them, applies updates, and is
  the single object spec 29 will drive. No transport here.
- Be correct under concurrency: applying two clients' updates in any order
  converges (CRDT property), and the bridge text is eventually consistent with
  the CRDT.

## 4. Non-goals (explicitly out of scope)

- The WebSocket endpoint, JWT auth, rooms, Redis fan-out — **spec 29**.
- Browser-side Yjs binding / CodeMirror integration — **spec 31**.
- Presence/cursor *UI* — **spec 32** (this spec only stores & relays the raw
  awareness bytes).
- Sharing, roles, and access control beyond what spec 13 already enforces —
  **specs 33/34**.
- Rich types beyond a single shared text per document (no `Map`/`Array`/
  subdocuments); the file tree stays in Postgres (spec 12).
- Undo/redo, history UI/diffing — **Phase 5** (this spec only *persists the log*
  that history will later consume).

## 5. Detailed requirements

### 5.1 Data model

New table `crdt_document_state` (1:1 with a spec-13 document) plus an append-only
`crdt_update` log. Ship an Alembic migration.

**`crdt_document_state`**
| column | type | constraints |
| --- | --- | --- |
| `document_id` | UUID (PK, FK → `documents.id` ON DELETE CASCADE) | the spec-13 document |
| `state` | BYTEA NOT NULL | latest full Yjs state snapshot (`Doc.get_update()` against empty state) |
| `state_vector` | BYTEA NOT NULL | state vector of `state` (`Doc.get_state()`) |
| `seq` | BIGINT NOT NULL DEFAULT 0 | monotonically increasing; bumped on each compaction |
| `text_synced_seq` | BIGINT NOT NULL DEFAULT 0 | last seq whose text was flushed to spec-13 `content` |
| `updated_at` | TIMESTAMPTZ NOT NULL | last write |

**`crdt_update`** (append-only log between snapshots)
| column | type | constraints |
| --- | --- | --- |
| `id` | BIGSERIAL PK | |
| `document_id` | UUID NOT NULL (FK → `documents.id` ON DELETE CASCADE), indexed | |
| `update` | BYTEA NOT NULL | a single binary Yjs update |
| `origin` | TEXT NULL | optional client/connection id for debugging & history attribution |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Index: `(document_id, id)` for ordered replay. Constraint/behaviour: on
compaction, rows with `id <=` the snapshotted high-water mark are deleted in the
same transaction that writes the new `state`/`state_vector`/`seq`.

> Awareness is **ephemeral** and is **not** persisted (it is per-connection,
> cleared on disconnect). It is held only in memory (see §5.2.4).

### 5.2 Backend / API (library contracts — no HTTP)

All under `backend/app/collab/`.

#### 5.2.1 Protocol encoding — `backend/app/collab/protocol.py`

Implement the standard **y-protocols** message framing so browser `y-websocket`/
`y-protocols` clients interoperate (spec 31 uses them). Messages are length/var-
int framed; reuse pycrdt's encoders/decoders where available rather than hand-
rolling varints.

Message types (outer tag byte):
- `MESSAGE_SYNC = 0` — body is a sync sub-message:
  - `SYNC_STEP_1 = 0` + state vector
  - `SYNC_STEP_2 = 1` + update
  - `SYNC_UPDATE = 2` + update
- `MESSAGE_AWARENESS = 1` — body is an awareness update blob.

Functions:
```python
def read_message(data: bytes) -> Message            # parse to a typed union
def encode_sync_step1(state_vector: bytes) -> bytes
def encode_sync_step2(update: bytes) -> bytes
def encode_update(update: bytes) -> bytes
def encode_awareness(awareness_update: bytes) -> bytes
```
`Message` is a discriminated union (e.g. `SyncStep1 | SyncStep2 | SyncUpdate |
AwarenessMessage | UnknownMessage`). Unknown tags decode to `UnknownMessage`
(ignored by callers, never raise).

#### 5.2.2 Document wrapper — `backend/app/collab/ydocument.py`

```python
class YDocument:
    TEXT_KEY = "content"
    def __init__(self, doc: pycrdt.Doc | None = None): ...

    @property
    def text(self) -> str: ...                       # current plain text
    def get_state(self) -> bytes: ...                # full state update (snapshot)
    def get_state_vector(self) -> bytes: ...
    def apply_update(self, update: bytes,
                     origin: str | None = None) -> None:
        """Apply a remote update inside a transaction tagged with origin."""
    def diff(self, remote_state_vector: bytes) -> bytes:
        """Update the peer with `remote_state_vector` is missing (for SYNC_STEP_2)."""
    def replace_text(self, new_text: str) -> bytes:
        """Set the shared text to new_text (used for initial load from spec-13);
        returns the produced update."""

    def observe(self, callback: Callable[[bytes, str | None], None]) -> None:
        """Register a callback fired with (update_bytes, origin) on every change,
        used by DocumentManager to relay + log updates."""
```

`apply_update`/local mutations must emit updates via the observer so the manager
can both **persist** (append to `crdt_update`) and **relay** (return to spec 29).

#### 5.2.3 Persistence — `backend/app/collab/store.py`

```python
class CrdtStore:
    def __init__(self, session_factory): ...  # async SQLAlchemy session factory

    async def load(self, document_id: UUID) -> tuple[bytes | None, int]:
        """Return (full_state_or_None, seq). Rebuilds full state by applying the
        snapshot then every crdt_update row in id order; None if no row & no
        spec-13 content yet."""
    async def append_update(self, document_id: UUID, update: bytes,
                            origin: str | None) -> None:
        """Append one update row. Cheap, on the hot path."""
    async def snapshot(self, document_id: UUID, state: bytes,
                       state_vector: bytes, upto_update_id: int | None) -> int:
        """Compaction: write state/state_vector, bump seq, delete crdt_update
        rows with id <= upto_update_id, in one transaction. Returns new seq."""
    async def mark_text_synced(self, document_id: UUID, seq: int) -> None: ...
```

Loading order is authoritative: **snapshot state first, then ordered updates**.
The append path must be O(1) and not read the whole log.

#### 5.2.4 Awareness — `backend/app/collab/awareness.py`

In-memory only. Wrap pycrdt's `Awareness` (or an equivalent) per document:
```python
class AwarenessRegistry:
    def apply(self, document_id: UUID, update: bytes) -> bytes:
        """Merge an awareness update; return the (possibly filtered) update to
        relay to other clients."""
    def remove_client(self, document_id: UUID, client_id: int) -> bytes | None:
        """Produce an awareness update marking a client offline (on disconnect)."""
    def snapshot(self, document_id: UUID) -> bytes | None:
        """Full awareness state to send to a newly joined client."""
```
No persistence; cleared when the last connection for a document leaves (spec 29
calls `remove_client`).

#### 5.2.5 Document manager — `backend/app/collab/manager.py`

The single object spec 29 drives. Owns in-memory `YDocument`s keyed by
`document_id`, with reference counting of open connections.

```python
class DocumentManager:
    def __init__(self, store: CrdtStore, content_bridge: "ContentBridge",
                 awareness: AwarenessRegistry, settings: CollabSettings): ...

    async def acquire(self, document_id: UUID) -> "OpenDocument":
        """Load (snapshot+log, or seed from spec-13 content on first ever open),
        register, return a handle. Increments refcount; loads lazily once."""
    async def release(self, document_id: UUID) -> None:
        """Decrement refcount; when it hits zero, flush text + snapshot, then
        evict from memory after an idle grace period (see config)."""

    async def handle_sync_step1(self, document_id, state_vector: bytes
                               ) -> tuple[bytes, bytes]:
        """Return (sync_step2_for_client, server_sync_step1) per the protocol."""
    async def handle_update(self, document_id, update: bytes, origin: str | None
                           ) -> bytes:
        """Apply, persist (append_update), schedule a text-bridge flush, and
        return the relayable update (for spec 29 to broadcast)."""
    async def handle_awareness(self, document_id, update: bytes) -> bytes: ...

    async def flush(self, document_id: UUID) -> None:
        """Force text bridge + (if log large) compaction now."""
```

Behaviour requirements:
- **Lazy load, single in-flight load** per document (guard with a lock so two
  concurrent `acquire`s don't double-load).
- **Compaction trigger:** after every `N` appended updates (config
  `COLLAB_SNAPSHOT_EVERY_UPDATES`) or `T` seconds since last snapshot (config
  `COLLAB_SNAPSHOT_INTERVAL_SECONDS`), run `store.snapshot` with the current
  state. Compaction must be safe to run concurrently with appends (snapshot
  captures a high-water-mark update id and only deletes `<=` it).
- **Idle eviction:** when refcount is 0 for `COLLAB_IDLE_EVICT_SECONDS`, flush
  and drop the in-memory doc to bound memory (no unbounded room growth — spec 30
  will stress this).

#### 5.2.6 Content bridge — `backend/app/collab/content_bridge.py`

```python
class ContentBridge:
    def __init__(self, document_service): ...  # spec-13 service
    async def load_initial_text(self, document_id: UUID) -> str:
        """Read spec-13 content for first-ever CRDT seed."""
    async def flush_text(self, document_id: UUID, text: str) -> None:
        """Write current CRDT text into spec-13 content so REST/compiler see it.
        Debounced by the manager; must be idempotent."""
```

The flush is **debounced** (config `COLLAB_TEXT_FLUSH_DEBOUNCE_MS`, default
1000ms) and also forced on `release`/`flush`. The spec-13 write path must not
itself re-emit a CRDT update (avoid a loop): the bridge writes the `content`
column directly via the document service's "set content from collab" seam (add a
narrow method if spec 13 doesn't expose one). On a first-ever open, if the CRDT
state is empty but spec-13 content is non-empty, seed the CRDT via
`replace_text`.

### 5.3 Frontend / UI

None. (Browser binding is spec 31.)

### 5.4 Real-time / jobs / external integrations

- **No WebSocket** here (spec 29). The manager exposes plain async methods.
- **No ARQ job required.** Persistence and compaction run inline in the manager
  (cheap; binary updates are small). Compaction is a quick DB transaction. If
  profiling later shows compaction is heavy for very large docs, it can be moved
  to ARQ in a future refactor — out of scope now.
- `pycrdt` is the only new dependency (add to backend deps).

### 5.5 Configuration

Add to a `CollabSettings` (Pydantic settings) and `.env.example`:
- `COLLAB_SNAPSHOT_EVERY_UPDATES` (default `200`) — compact after this many
  appended updates.
- `COLLAB_SNAPSHOT_INTERVAL_SECONDS` (default `30`) — or after this long.
- `COLLAB_TEXT_FLUSH_DEBOUNCE_MS` (default `1000`) — debounce for the spec-13
  text bridge.
- `COLLAB_IDLE_EVICT_SECONDS` (default `300`) — evict idle in-memory docs.
- `COLLAB_MAX_UPDATE_BYTES` (default `1048576`, 1 MiB) — reject a single update
  larger than this (returns/raises a typed error the transport maps later); guards
  against abuse.
- No secrets.

## 6. Overleaf reference (study only — never copy)

> Overleaf uses **OT (ShareJS)**, a different algorithm. Read for the operational
> concerns of live-doc state and flushing — never the merge logic.

- `services/document-updater/app/js/DocumentManager.js`,
  `RedisManager.js`, `PersistenceManager.js`, `ProjectFlusher.js` — how a live
  in-memory document is held, how state is loaded/flushed to the persistent store,
  and how flushing is triggered/debounced. Learn the lifecycle (load → mutate →
  flush → evict); Inkstave's store is Postgres + a CRDT snapshot/log, not Redis +
  OT ops.
- `libraries/overleaf-editor-core/lib/` (e.g. `change.js`, `chunk.js`,
  `snapshot.js`) — the *concept* of snapshot + change-log compaction. Learn the
  snapshot/compaction idea; Inkstave stores binary Yjs updates, not OT changes.

## 7. Acceptance criteria

1. **Round-trip text.** Creating a `YDocument`, `replace_text("Hello")`, reading
   `.text` returns `"Hello"`; `get_state()` re-applied to a fresh `YDocument`
   reproduces `"Hello"`.
2. **Sync protocol.** Given two `YDocument`s A and B that have diverged,
   exchanging Step1(state vector)→Step2(diff) in both directions makes A and B
   converge to identical `.text` and identical state vectors.
3. **Convergence under reorder.** Applying updates u1 then u2 to one doc and u2
   then u1 to another (both from a shared base) yields identical `.text` (CRDT
   commutativity), verified for concurrent inserts at the same position.
4. **Persistence load order.** With a snapshot plus three appended updates,
   `CrdtStore.load` rebuilds the exact current state (snapshot then ordered log).
5. **Compaction.** After `snapshot(upto_update_id=X)`, `crdt_update` rows with
   `id <= X` are gone, `seq` increased, and a subsequent `load` still reproduces
   the same `.text`.
6. **Append is O(1).** `append_update` performs a single INSERT and does not read
   the existing log (assert via query count / instrumentation).
7. **Bridge: CRDT → spec-13.** After applying an update that changes the text and
   forcing `flush`, the spec-13 `content` for that document equals the CRDT
   `.text`, and the compiler/REST read path returns the new text.
8. **Bridge: spec-13 → CRDT seed.** Opening a document whose CRDT state is empty
   but whose spec-13 `content` is `"Seed"` seeds the CRDT so `.text == "Seed"`.
9. **No bridge loop.** A bridge `flush_text` write does not itself generate a new
   `crdt_update` row.
10. **Awareness relay.** Applying an awareness update merges it and returns a
    relayable blob; `snapshot` returns full awareness; `remove_client` produces
    an offline update. Nothing is written to the database.
11. **Manager lifecycle.** Two concurrent `acquire`s of the same document load it
    exactly once; after `release` to refcount 0 and the idle grace period, the
    in-memory doc is evicted (memory does not grow per open/close cycle).
12. **Update size guard.** An update larger than `COLLAB_MAX_UPDATE_BYTES` is
    rejected with a typed error.
13. **Budget.** All spec-28 tests run in well under the 2-minute global budget
    (target < 10s; pure CRDT + DB unit/integration, no network/transport).

## 8. Test plan

> Fast, unit-testable: CRDT logic is pure Python; persistence uses the test DB.
> No WebSocket here (that's spec 29) so no async client is needed.

- **Unit (pytest):**
  - `protocol.py`: encode/decode round-trips for every message type; unknown tag
    → `UnknownMessage`; malformed bytes do not crash callers.
  - `ydocument.py`: text round-trip, `get_state`/`get_state_vector`/`diff`,
    `replace_text`, observer fires with `(update, origin)`, convergence &
    commutativity (criteria 2–3) using two in-memory docs.
  - `awareness.py`: merge/snapshot/remove_client (criterion 10).
  - Config bounds: update size guard (criterion 12).
- **Integration (pytest + test DB):**
  - `store.py`: load order, snapshot/compaction + row deletion, append O(1)
    (criteria 4–6) — use a real (test) Postgres or the project's standard
    transactional test DB fixture.
  - `manager.py` + `content_bridge.py`: lazy single load under concurrency, flush
    bridges text to spec-13 and back-seeds (criteria 7–9, 11), idle eviction with
    a shrunk grace period set via settings.
- **Performance/budget note:** binary updates are tiny; compaction is one
  transaction; eviction timers use injected/short intervals in tests. No real
  network, no transport, no LLM, no LaTeX. Use `pytest-asyncio` and the existing
  fast DB fixtures from spec 03/04.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (protocol, YDocument, store, awareness,
      manager, content bridge, migration).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright).
- [ ] Alembic migration for `crdt_document_state` + `crdt_update` shipped (never
      edit a released migration).
- [ ] New `COLLAB_*` env vars documented in `.env.example`; an ADR in `docs/`
      records the snapshot/compaction strategy and the CRDT↔REST bridge.
- [ ] No Overleaf code copied; the CRDT design is independent of Overleaf's OT.
