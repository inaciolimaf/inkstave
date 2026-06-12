# ADR 0031 — Frontend Yjs binding: persistence/reconciliation & REST-autosave retirement

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 31 — Frontend Yjs binding & live sync

## Context

Spec 31 makes editing live and collaborative on the client: a `Y.Doc` per open
document, bound to CodeMirror via `y-codemirror.next`, synced over the spec-29
JWT WebSocket through a custom `InkstaveWsProvider`. The open question this ADR
settles: **what persists the text, and how does the REST/compile view stay
current** once live edits flow over the CRDT instead of REST autosave.

## Decisions

### 1. The server (spec 28) is the single persistence path — client REST autosave is retired for collab documents

Spec 28's `DocumentManager` already persists **every applied CRDT update** to
`crdt_update` and materialises the current text into the spec-13 `content` column
via its (debounced + flush-on-release) content bridge. There is therefore **no
reason for the client to also PUT the full document on every keystroke** — that
would double-write and fight the CRDT.

So: when collaboration is enabled (`VITE_COLLAB_WS_URL` set — the default,
derived from the API origin), a document opens in the **`CollabEditor`** which
uses the `y-codemirror.next` binding and **does not run the spec-19 REST
autosave**. The single-user REST autosave editor remains as the fallback only
when collaboration is disabled (`VITE_COLLAB_WS_URL=""`). This is gated in
`EditorPane` by a `collabEnabled` flag (default **false**, so the existing
single-user editor and its tests are unchanged); `EditorWorkspace` turns it on
from config in the running app.

### 2. The client never seeds the CRDT — spec 28 does

Spec 28 already seeds an empty CRDT from the stored spec-13 content on first ever
open. The client therefore **never seeds**: it opens an empty `Y.Doc`, runs the
sync handshake, and the server's Sync Step 2 delivers the current text. This
avoids the double-insert race the spec warns about.

### 3. Compile sees current text via `session.flush()` + the server bridge

The compile path (spec 22) assembles from the spec-13 `content` column, which the
spec-28 bridge keeps in sync with the CRDT. To ensure a compile reflects the
**latest local keystrokes**, the client exposes `await session.flush()` (resolves
once pending local updates have been **sent** and the socket buffer drained) to be
called before triggering a compile. Because the server applies and persists each
update as it arrives, once `flush()` resolves the server holds every local edit.

**Known window (documented, not fixed here):** the server's CRDT→content
materialisation is debounced (spec-28 `COLLAB_TEXT_FLUSH_DEBOUNCE_MS`, 1 s), so a
compile fired immediately after `flush()` could read text up to ~1 s stale. We do
**not** change the backend (out of scope for spec 31). A clean follow-up is a
compile-time force-flush in spec 22; until then the debounce is short enough for
practical use and the client `flush()` guarantees no *lost* edits.

### 4. Connection lifecycle

`InkstaveWsProvider` is a minimal y-websocket-style provider over `y-protocols`
(`sync`/`awareness`) + `lib0`, matching spec-29's framing exactly (a var-uint
message type then a sync/awareness body). State machine
`idle → connecting → connected → (reconnecting ⇄ connected) → closed`; reconnect
with **exponential backoff (500 ms base, 15 s cap, full jitter)**, resyncing on
every (re)connect. `synced` flips true on the first Sync Step 2 and **stays true**
so edits remain allowed while reconnecting (offline edits accumulate in the
`Y.Doc` and merge on resync). `destroy()` is idempotent (StrictMode-safe), removes
listeners, closes the socket, and stops reconnecting. The JWT is taken from the
auth layer via an injected `getToken` and sent as the spec-29 `?token=` query
param; it is verified once at the handshake and the session is **kept until
disconnect** (no per-message re-verification — matches spec 30's policy).

### 5. Editing is gated on first sync

Until `synced === true` the editor is shown read-only with a "Loading document…"
overlay, so a user can't type into an un-synced doc and create a divergent base.
A toolbar `Badge` (`aria-live="polite"`) reflects the connection status: green
"Live", amber "Connecting…/Reconnecting…", grey "Offline". Undo/redo is scoped to
the local user via `y-codemirror.next`'s undo manager.

## Consequences

- New module `frontend/src/features/collab/` (`InkstaveWsProvider`, `useCollabDoc`,
  `CollabEditor`, `ConnectionStatusBadge`). New deps: `yjs`, `y-codemirror.next`,
  `y-protocols`, `lib0`. New `VITE_COLLAB_WS_URL` (default-on, derived).
- `CodeMirrorEditor` gained an optional `collabExtension` (collab mode: the CRDT
  owns content; `doc`/`onChange` unused) — additive, existing callers unchanged.
- Heavy convergence/reconnect/echo tests run as in-process Vitest against a fake
  spec-29 relay; one Playwright two-context e2e (`e2e/collab.spec.ts`) is the only
  browser-level assertion, gated behind the e2e tier (not the 2-minute budget).
- The existing single-user editor e2e (`e2e/editor.spec.ts`) assumes REST editing;
  with collab default-on it would need a WS mock or `VITE_COLLAB_WS_URL=""` in the
  e2e build — flagged for the e2e tier owner.
