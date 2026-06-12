# Spec 31 — Frontend Yjs binding & live sync (requirements)

## 1. Summary

This spec makes editing live and collaborative on the client side. It introduces
a Yjs document for each open project document, binds that Yjs text to the
CodeMirror 6 editor via `y-codemirror.next`, and connects a custom Yjs provider
to the JWT-authenticated collaboration WebSocket from spec 29. Live edits now
flow as binary Yjs updates over the WebSocket instead of the single-user REST
autosave from spec 19; the REST/compile view of content is reconciled against
the CRDT so compilation still sees the current text.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 29** — collaboration WebSocket: a JWT-authed `ws(s)://.../api/v1/collab/projects/{projectId}/ws`-style endpoint, a per-document "room", and a binary message protocol that carries Yjs **sync** (sync-step-1/2) and **update** messages plus an **awareness** channel. This spec uses the sync + update channels only.
  - **Spec 28** — pycrdt server document: the authoritative server-side Yjs document whose state the client syncs against on join, and which persists updates.
  - **Spec 19** — the existing single-user editor wiring: the CodeMirror instance, the "open document" lifecycle, and REST autosave (`PUT /api/v1/projects/{id}/docs/{docId}`) which this spec largely supersedes for live editing.
  - **Spec 18** — CodeMirror 6 editor, LaTeX language support, editor state management.
- **Unlocks:**
  - **Spec 32** — presence/awareness UI reuses this provider's awareness channel and the shared `Y.Doc`.
  - **Spec 34** — access control plumbs a `readOnly` capability into the binding established here.
  - **Spec 36** — history capture observes the same CRDT updates.
- **Affected areas:** frontend (editor, collab client, API client), docs.
  No backend changes (spec 29 is consumed as-is). No database changes.

## 3. Goals

- Maintain one `Y.Doc` per open document, with a `Y.Text` named `content` as the
  single shared text type. (The name `content` is fixed and must match spec 28.)
- Bind that `Y.Text` to the CodeMirror 6 `EditorView` with `y-codemirror.next`'s
  `yCollab`/`ySync` extension so local edits mutate the CRDT and remote updates
  apply to the editor — with no echo loops and correct undo scoping.
- Implement a **custom Yjs provider** (`InkstaveWsProvider`) that:
  - opens the spec-29 WebSocket with the JWT,
  - performs the initial **sync** (sync step 1 → 2 → 1) to load server state,
  - relays subsequent local/remote **updates**,
  - exposes the `awareness` instance for spec 32 (created here, populated later).
- Handle connection lifecycle: connecting, connected, reconnecting (exponential
  backoff with jitter), offline, and a clean teardown when the document closes.
- Allow **offline editing**: while disconnected, edits accumulate in the local
  `Y.Doc`; on reconnect, a fresh sync merges them with the server with no loss
  and no manual conflict resolution.
- Reconcile with the REST/compile path: compilation (spec 22) and any REST read
  must observe the current CRDT text. Define exactly how (see §5.4).
- Expose a connection-status indicator value to the editor UI (a small badge;
  full presence UI is spec 32).

## 4. Non-goals (explicitly out of scope)

- Remote cursors, selections, name/color rendering, "online now" avatars — **spec 32**.
- Sharing, invites, roles — **spec 33**.
- Enforcing viewer read-only at the protocol/authz level — **spec 34**. Here the
  binding accepts a `readOnly` boolean that defaults to `false`/editable.
- Server-side CRDT model or WebSocket protocol changes — owned by **specs 28/29**.
- Version history snapshots/restore — **spec 36+**.
- IndexedDB offline persistence across page reloads (in-memory `Y.Doc` only this
  spec; persistence is not required and is out of scope unless a later spec adds it).

## 5. Detailed requirements

### 5.1 Data model

No database or backend schema changes. Client-side runtime state only:

- `Y.Doc` (per open document) holding `ydoc.getText('content')`.
- `Awareness` (from `y-protocols/awareness`) created alongside the doc; **not**
  populated with cursor/user fields in this spec (spec 32 does that). It is wired
  through the provider so spec 32 needs no provider changes.
- A `CollabDocSession` object (see §5.3) tying together `Y.Doc`, provider,
  awareness, CodeMirror binding extension, and status.

### 5.2 Backend / API

None new. This spec **consumes**:

- Spec 29 WebSocket endpoint (exact path/handshake defined by spec 29; reference
  it via the frontend API/config layer, do not hardcode in components).
- Spec 19 REST document endpoints, retained for initial document metadata/open
  and as the reconciliation source for compile (see §5.4).

The implementer must read spec 29's message framing and implement the client
half. Expected framing (must be confirmed against the spec-29 implementation):

| Message kind | Direction | Payload |
| --- | --- | --- |
| `sync` (step 1) | both | Yjs sync protocol state-vector message |
| `sync` (step 2) | both | Yjs sync protocol update (full or diff) |
| `update` | both | Yjs document update (binary) |
| `awareness` | both | awareness update (binary) — relayed only, used by spec 32 |

Encoding: use `y-protocols/sync` (`writeSyncStep1`, `readSyncMessage`, etc.) and
`lib0/encoding`,`lib0/decoding`, matching whatever spec 29 implemented on the
server. If spec 29's framing differs, adapt the client to it (spec 29 is
authoritative for wire format); do **not** modify the server.

### 5.3 Frontend / UI

**New module: `frontend/src/features/collab/`**

- `InkstaveWsProvider.ts` — the custom provider class:
  - Constructor: `(opts: { url: string; documentId: string; ydoc: Y.Doc; awareness: Awareness; getToken: () => string | Promise<string> })`.
  - Authenticates by sending the JWT exactly as spec 29 expects (query param or
    first message — match spec 29). Tokens are obtained from the existing auth
    layer (spec 07–09), never read from `localStorage` directly in this module;
    inject via `getToken`.
  - State machine: `idle → connecting → connected → (reconnecting ⇄ connected) → closed`.
  - On open: send sync step 1; on receiving server sync, apply it; mark
    `synced = true` and fire a `synced` event once the first full sync completes.
  - On local `ydoc.update`: encode and send an `update` message (skip updates
    whose origin is the provider itself, to avoid echo).
  - On remote `update`: apply with the provider as origin.
  - Reconnect: exponential backoff starting 500 ms, cap 15 s, full jitter; reset
    on successful connect. Resync (sync step 1) on every (re)connect.
  - `destroy()`: remove listeners, close socket, no further reconnects.
  - Emits events: `status` (`{status}`), `synced` (`{synced:boolean}`),
    `connection-error`.
- `useCollabDoc.ts` — a React hook returning a `CollabDocSession`:
  ```ts
  interface CollabDocSession {
    ydoc: Y.Doc
    text: Y.Text            // ydoc.getText('content')
    provider: InkstaveWsProvider
    awareness: Awareness
    status: 'connecting' | 'connected' | 'reconnecting' | 'offline'
    synced: boolean
    cmExtension: Extension  // the y-codemirror.next collab extension
    readOnly: boolean       // default false; consumed in spec 34
  }
  ```
  - Creates exactly one session per `documentId`; tears it down on unmount or
    when `documentId` changes. Guards against React StrictMode double-mount
    (idempotent create; destroy is safe to call twice).

**Editor integration (modifies spec 18/19 editor):**

- Replace the spec-19 REST-autosave-driven content source with the Yjs binding
  when the collab session is available:
  - Add `cmExtension` (from `y-codemirror.next`) to the `EditorView`
    configuration for the open document.
  - The editor must **not** also push the full document via REST autosave on
    every keystroke (that would double-write and fight the CRDT). See §5.4 for
    what remains of REST.
  - Until `synced === true`, the editor for that document is shown read-only /
    "loading" so the user can't type into an un-synced doc and create a divergent
    base. After first sync, it becomes editable (subject to `readOnly`).
- Use `y-codemirror.next`'s undo manager (`yUndoManagerKeymap` / the binding's
  undo) so undo/redo is scoped to the local user's changes only.

**Connection status badge:**

- A small shadcn/ui `Badge` (or `Tooltip`-wrapped dot) in the editor toolbar
  reflecting `status`: green "Live", amber "Reconnecting…", grey "Offline".
  Full presence avatars are spec 32.

**States & UX:**

- *Connecting / not yet synced:* editor disabled with a subtle skeleton/overlay;
  badge amber "Connecting…".
- *Connected & synced:* editor editable; badge green "Live".
- *Reconnecting:* editor stays editable (offline edits allowed), badge amber.
- *Closed/error:* badge grey "Offline"; provider keeps retrying unless the doc
  is closed.
- Accessibility: badge has `aria-live="polite"` text; disabled editor has an
  accessible "Loading document…" label.

### 5.4 Real-time / reconciliation

**WebSocket usage:** as in §5.2. Exactly one WebSocket connection per project is
acceptable if spec 29 multiplexes documents over one socket; otherwise one per
open document — follow spec 29's room design. The provider must not assume more
than spec 29 guarantees.

**Reconciliation with REST/compile — required design:**

- The CRDT is the source of truth for live text. The server (spec 28) persists
  CRDT updates and can materialize the current text. Therefore:
  - **Compile (spec 22) reads server-materialized CRDT text**, not stale REST
    rows. The client does **not** need to flush text before compiling, because
    the server already holds every applied update. The client only needs to
    ensure its pending local updates have been sent (provider `synced` and its
    outbound queue drained) — expose `await session.flush()` that resolves when
    the local update queue is empty and acked-or-sent, and call it before
    triggering a compile.
  - **REST document read (open):** opening a document still fetches metadata via
    spec 19/13 REST, but the *content* shown comes from the CRDT sync. If the
    server's CRDT for a never-collaborated document is empty, the provider seeds
    it from the REST content **once**, guarded so two clients racing to seed do
    not double-insert (seed only if `text.length === 0` after first sync *and*
    the client is the room initiator — or simpler: server seeds in spec 28; if
    spec 28 already seeds from stored content, the client never seeds and this
    bullet is a no-op — prefer that and document which is true).
  - **REST autosave (spec 19) is retired as the live channel.** Keep at most a
    low-frequency "snapshot to REST/DB for compile fallback" only if spec 28 does
    *not* already persist; if spec 28 persists CRDT state, remove client REST
    autosave entirely for collab docs and record this in `docs/`.

State this resolved choice explicitly in `docs/` (ADR): whether the server
(spec 28) is the single persistence path, or the client retains a snapshot
fallback. Prefer the server-only path.

### 5.5 Configuration

- `VITE_COLLAB_WS_URL` (frontend env) — base URL/path for the spec-29 WebSocket;
  default derived from the API origin (e.g. same origin, `/api/v1/collab`).
  Added to `frontend/.env.example`.
- Reconnect tuning constants live in `InkstaveWsProvider` as named constants, not
  env vars.
- No new backend env vars.

## 6. Overleaf reference (study only — never copy)

> Overleaf uses ShareJS/OT over Socket.IO, **not** Yjs/CRDTs. Study only the
> *lifecycle and binding approach*; the data model and wire format are entirely
> different and must be implemented independently against spec 28/29.

- `services/web/frontend/js/features/ide-react/connection/connection-manager.ts`
  — how a client manages connect/disconnect/reconnect, backoff, and a connection
  state machine. Learn the *shape* of the lifecycle, not the transport.
- `services/web/frontend/js/features/ide-react/connection/editor-watchdog-manager.ts`
  — detecting a stalled/dead connection. Adapt the idea to a WS heartbeat/resync.
- `services/web/frontend/js/features/ide-react/connection/join-project-payload.ts`
  — what a client sends/expects on join. Inkstave's join is a Yjs sync, not this.
- `services/web/frontend/js/features/source-editor/extensions/realtime.ts`
  — how the editor is bound to the realtime layer (OT here). Inkstave uses
  `y-codemirror.next` instead; learn how the extension hooks editor lifecycle.
- `services/web/frontend/js/features/source-editor/extensions/before-change-doc.ts`,
  `effect-listeners.ts` — how local changes are intercepted before propagation.
  For Yjs this is handled by the binding; study only to understand echo/loop
  prevention concerns.

If a capability has no Overleaf equivalent (e.g. Yjs sync-step negotiation), it
has none — implement from `y-protocols`.

## 7. Acceptance criteria

1. **Given** an open document and a running spec-29 WebSocket, **when** the
   editor mounts, **then** the provider connects, completes the Yjs sync, fires
   `synced`, and the editor becomes editable showing the server's current text.
2. **Given** two in-process Yjs clients sharing one server room, **when** client
   A inserts text, **then** client B's `Y.Text` contains that text after the
   update propagates (verified without a real browser).
3. **Given** a connected client, **when** the WebSocket drops, **then** the badge
   shows "Reconnecting…", local edits still apply to the local `Y.Doc`, and the
   provider retries with exponential backoff.
4. **Given** a client that edited while offline, **when** the connection is
   restored, **then** a fresh sync merges its offline edits with concurrent
   server edits with no lost characters and no duplication.
5. **Given** local edits typed in the editor, **then** they appear as `update`
   messages on the wire and do **not** echo back into the editor as duplicate
   insertions (no loop).
6. **Given** `synced === false`, **then** the editor for that document is not
   editable and shows a loading state; it becomes editable only after first sync.
7. **Given** the document is closed or the component unmounts, **then** the
   provider stops retrying, the socket closes, and no listeners leak (verified by
   a teardown assertion).
8. **Given** a compile is triggered, **when** `session.flush()` resolves, **then**
   the server's materialized text reflects the latest local edits (compile sees
   current content; verified via the reconciliation path, server stubbed/real per
   test tier).
9. **Given** undo after typing, **then** undo reverts only the local user's most
   recent change group, not remote edits.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> The two-client collab test uses **two in-process Yjs `Y.Doc`s wired through a
> fake/in-memory transport (or a real spec-29 server in a single test)**, not two
> browsers, to stay fast. Exactly **one** minimal Playwright two-context e2e.

- **Unit (Vitest):**
  - `InkstaveWsProvider` state machine: transitions idle→connecting→connected→
    reconnecting→closed using a mock WebSocket; backoff schedule (mock timers);
    no reconnect after `destroy()`.
  - Echo prevention: local update produces an outbound message but is not
    re-applied; remote update applies once.
  - `useCollabDoc` lifecycle: single session per `documentId`; idempotent under
    StrictMode double-mount; teardown closes provider and removes listeners.
  - Editor gating: editor disabled until `synced`, editable after.
- **Integration / collab (Vitest, in-process):**
  - Two `Y.Doc`s + two providers connected through an in-memory relay that mimics
    spec-29 framing (or, if cheap, a single instance of the real spec-29 server):
    edits on A converge on B (AC 2); offline-then-reconnect convergence (AC 4);
    concurrent inserts converge identically on both (CRDT property).
  - `session.flush()` resolves after outbound queue drains; reconciliation places
    current text where compile reads it (server materialization stubbed).
- **E2E (Playwright, minimal — one test):**
  - Two browser contexts open the same document; typing in context A appears in
    context B's editor within a short timeout. Keep to a single spec to protect
    the budget; this is the only browser-level collab assertion.
- **Performance/budget note:** the heavy convergence/property tests run as
  in-process Vitest (milliseconds). Only one Playwright two-context test touches
  a real browser/WS. No LaTeX compile is run in these tests (compile is mocked;
  only the reconciliation contract is asserted).

## 9. Definition of Done

- [ ] All requirements in §5 implemented (`InkstaveWsProvider`, `useCollabDoc`,
      `y-codemirror.next` binding, status badge, reconciliation path).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; exactly one Playwright two-context test.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (TS strict).
- [ ] `VITE_COLLAB_WS_URL` documented in `frontend/.env.example`; ADR in `docs/`
      recording the persistence/reconciliation decision and REST-autosave retirement.
- [ ] No Overleaf code copied; only Yjs + `y-codemirror.next` used for collab.
