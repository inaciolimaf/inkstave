# Spec 19 — Document Autosave (REST) (requirements)

## 1. Summary

This spec turns the read-only editor from spec 18 into a **single-user editable**
editor with **debounced autosave over REST**. Edits are buffered locally and
flushed to the spec 13 version-checked replace-content endpoint after a short
debounce (and on blur / before unload). A **dirty / saving / saved** indicator
communicates state. Optimistic-concurrency **version conflicts** (the server's
version moved past ours) are detected and handled with a reload/merge prompt.
Offline / transient failures are retried with backoff. This is the pre-realtime
baseline; Phase 4's CRDT sync will replace or augment it. **No realtime,
multi-user, or WebSocket work here.**

## 2. Context & dependencies

- **Depends on:**
  - **18** — editable CodeMirror 6 pane (flip read-only → editable via the
    existing compartment) + the IDE shell, the document fetch (content+version),
    the editor store/selection.
  - **13** — document content API, specifically the **replace-content** endpoint
    that takes the client's base **version** and applies optimistic concurrency
    (returns the new version, or a 409 on mismatch).
- **Unlocks:**
  - Phase 4 realtime (28+) replaces this REST sync with CRDT sync; the dirty/
    saved UX and conflict concepts carry over.
- **Affected areas:** frontend only (consumes spec 13's existing endpoint).

> **API contract note.** The replace-content endpoint, its version semantics and
> its 409 conflict response are defined by **spec 13** and are authoritative.
> This spec assumes the contract in §5.4; adapt if spec 13 differs.

## 3. Goals

- Make the editor editable (single user): remove the read-only facets from spec
  18 via the existing compartment.
- Track local document state: current text, last-saved text, base version.
- **Debounced autosave**: after N ms of inactivity (default ~1000 ms), and also
  on editor blur, document switch, and `beforeunload`/`visibilitychange`, flush
  pending changes to the server.
- Send the base **version** with each save; on success, advance to the returned
  version and mark clean.
- **Conflict handling**: on a 409 version mismatch, do not silently overwrite —
  present a clear prompt (reload server version / keep mine) and resolve safely.
- **Offline / retry**: detect failures and `navigator.onLine`; retry with
  backoff; surface an "unsaved / offline" state; never lose buffered edits.
- **Status indicator**: visible saved / saving / unsaved / error states.
- Guard against navigating away with unsaved changes (in-app + browser prompt).
- Accessibility: status is announced; the editor remains keyboard-first.

## 4. Non-goals (explicitly out of scope)

- Multi-user realtime, presence, CRDT, OT, WebSocket (specs 28+).
- Three-way text **merge** UI/algorithm — conflict resolution here is
  reload-or-overwrite (a real merge belongs to history/realtime later). A simple
  side-by-side "yours vs server" view is acceptable but auto-merging is not
  required.
- Per-keystroke saving or server-side incremental patches; this spec sends the
  full document content (matching spec 13's replace-content contract).
- Saving binary files, renaming, or moving (covered by spec 17).
- History/versioning beyond the single integer optimistic-concurrency version.
- Compile/preview.

## 5. Detailed requirements

### 5.1 Data model (if any)

None on the server. Per-open-document client state:

```ts
// frontend/src/features/editor/autosave/types.ts
export type SaveStatus =
  | 'clean'          // matches server, nothing pending
  | 'dirty'          // local edits not yet flushed
  | 'saving'         // a save request is in flight
  | 'error'          // last save failed (will retry)
  | 'offline'        // no connectivity; queued
  | 'conflict';      // server version moved; awaiting user decision

export interface DocAutosaveState {
  documentId: string;
  baseVersion: number;     // version the current text is derived from
  serverText: string;      // last text we know the server holds (for conflict diff)
  localText: string;       // current editor text
  status: SaveStatus;
  lastSavedAt: number | null;
  retryCount: number;
}
```

### 5.2 Backend / API (if any)

None added. Consumes spec 13 (§5.4).

### 5.3 Frontend / UI

#### 5.3.1 Component / hook structure

```
EditorPane (from spec 18, extended)
├── CodeMirrorEditor              (editable now; reports doc changes via updateListener)
├── SaveStatusIndicator          (badge in EditorPaneHeader: Saved / Saving… / Unsaved / Error / Offline)
├── useDocumentAutosave(documentId)   (the autosave hook/state machine)
└── ConflictDialog                (shadcn Dialog: shown on 409)
        ├── "Reload server version" (discard local)
        ├── "Overwrite with mine"   (re-save local against new server version)
        └── (optional) side-by-side diff (yours | server)
UnsavedChangesGuard                (router prompt + beforeunload listener)
```

#### 5.3.2 The autosave hook / state machine

`useDocumentAutosave(documentId)`:

- Seeds state from spec 18's fetched `{ content, version }` → `baseVersion`,
  `serverText`, `localText`, `status: 'clean'`.
- Subscribes to CodeMirror changes (an `EditorView.updateListener` that fires on
  doc changes) → updates `localText`, sets `status: 'dirty'`, schedules a
  debounced flush.
- **Flush** (`saveNow`):
  1. If not dirty or already saving → no-op.
  2. Set `status: 'saving'`. `PUT/PATCH` replace-content with
     `{ content: localText, version: baseVersion }`.
  3. **200**: set `baseVersion = response.version`, `serverText = localText`,
     `status: 'clean'`, `lastSavedAt = now`, `retryCount = 0`.
  4. **409 conflict**: set `status: 'conflict'`, open `ConflictDialog`. Do not
     overwrite. Fetch the latest server content+version for the diff/reload.
  5. **Network/5xx / offline**: set `status: 'error'`/`'offline'`, increment
     `retryCount`, schedule a backoff retry (e.g. 1s, 2s, 4s, capped). Keep
     buffered edits.
- **Triggers to flush:** debounce timer (~1000 ms after last edit), editor blur,
  switching documents (flush the outgoing doc first), `visibilitychange` to
  hidden, and `beforeunload` (best-effort synchronous flush /
  `navigator.sendBeacon` if the endpoint supports it; otherwise warn).
- **Online recovery:** on `window` `online` event, if dirty/error/offline,
  attempt a flush.
- Cancels timers and unsubscribes on unmount / document change.

#### 5.3.3 Save status indicator

- A compact badge in the editor header reflecting `status`:
  - `clean` → "Saved" (+ relative time, e.g. "Saved just now").
  - `dirty` → "Unsaved changes".
  - `saving` → "Saving…" (spinner).
  - `error` → "Save failed — retrying" (with a manual **Retry** affordance).
  - `offline` → "Offline — changes will save when you reconnect".
  - `conflict` → "Conflict" (links to the dialog).
- Implemented with shadcn `Badge`/`Tooltip`; status text is in an `aria-live`
  region so screen readers hear transitions.

#### 5.3.4 Conflict dialog

- Opens on 409. Explains: "This document changed on the server since you opened
  it." Offers:
  - **Reload server version** — discards local edits, replaces the editor with
    the latest server content+version, `status: 'clean'`. (Confirm if local
    edits are non-trivial.)
  - **Keep my version** — re-saves `localText` against the *new* server version
    (i.e. rebase the version and overwrite), then `status: 'clean'`.
  - Optional side-by-side read-only diff (yours | server) to inform the choice.
- The dialog is a shadcn `Dialog`/`AlertDialog`, focus-trapped, Esc cancels
  (leaving status `conflict` until resolved).

#### 5.3.5 Unsaved-changes guard

- In-app navigation away from a dirty/saving doc (router) prompts
  "You have unsaved changes — leave anyway?" using the router's blocker +
  a shadcn `AlertDialog`.
- A `beforeunload` handler warns on full-page unload while dirty.

#### 5.3.6 User interactions

1. **Type** → status goes `dirty`, then `saving`, then `clean` after the
   debounce+request succeed.
2. **Switch documents** with unsaved changes → flush the outgoing doc before
   loading the next.
3. **Lose connection** mid-edit → status `offline`; edits keep buffering;
   reconnect → auto-flush.
4. **Concurrent change** (another tab/session bumped the version) → next save
   gets 409 → conflict dialog → user resolves.
5. **Manual save** (optional `Ctrl/Cmd+S`) forces an immediate flush and
   `preventDefault`s the browser save dialog.

#### 5.3.7 Validation

- Do not send a save if `localText === serverText` (nothing changed).
- Guard against overlapping in-flight saves (single-flight; coalesce — if edits
  arrive during a save, mark dirty and flush again after it resolves).
- Clamp/cap retry backoff and retry count; after the cap, stay in `error` with a
  manual retry available (never busy-loop).

#### 5.3.8 Loading / empty / error states

- Inherits spec 18's load/empty/error for opening a document.
- Save errors are shown via the status indicator (not a blocking modal), except
  conflicts (dialog) and the leave-guard (dialog).

#### 5.3.9 Accessibility

- Status transitions are announced via `aria-live="polite"`.
- Conflict and leave-guard dialogs are focus-trapped shadcn primitives with
  clear, labelled actions; destructive "discard my edits" is clearly marked and
  not the default focus.
- `Ctrl/Cmd+S` shortcut documented and not stealing focus.
- The editor remains fully keyboard-operable; saving never moves focus.

### 5.4 Real-time / jobs / external integrations

Consumes **spec 13** via the spec 09 API client. No WebSocket, no ARQ here.

| Action | Method & path (spec 13) | Body | Success | Conflict/Errors |
| --- | --- | --- | --- | --- |
| Replace content (versioned) | `PUT /projects/{pid}/docs/{docId}/content` (or spec 13's path) | `{ content: string, version: number }` | `200` `{ version: number }` | **`409`** version mismatch (returns/implies latest server version); `404`,`403`,`401`,`5xx` |
| Get content (for conflict reload) | `GET …/docs/{docId}` | – | `200` `{ content, version }` | as above |

> The **optimistic-concurrency contract** (send base version, get 409 on
> mismatch, receive the new version on success) is spec 13's. If spec 13 uses
> ETag/If-Match headers instead of a body `version`, follow that. Keep all HTTP
> in `frontend/src/features/editor/api.ts`.

### 5.5 Configuration

- Tunable client constants (in code, documented): debounce delay (default
  1000 ms), retry backoff schedule + cap. No new env vars.
- No new server config.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for the **approach only**. Paths verified.

- `services/web/frontend/js/features/ide-react/editor/` (e.g.
  `document-container.ts`, `open-documents.ts`) — how Overleaf tracks open
  documents, buffers changes and coordinates saving (concept only; Inkstave's
  model is much simpler: REST + integer version).
- `services/document-updater/` (the service directory) — the *concept* of a
  document-updater that batches/flushes edits and resolves versions. Inkstave's
  baseline does this client-side over REST; study the idea, write your own.
- `services/web/frontend/js/features/source-editor/extensions/` — for the
  `updateListener`/change-tracking pattern in CodeMirror 6 (concept only).

Inkstave differences: single-user, full-content REST replace with an integer
optimistic-concurrency version (no OT/CRDT, no document-updater service, no
WebSocket). The Phase 4 specs replace this with CRDT sync.

## 7. Acceptance criteria

1. **Given** an open document, **then** the editor is editable (spec 18's
   read-only facets are removed) and typing changes the buffer.
2. **Given** the user types and then pauses, **then** after the debounce the
   client sends a replace-content request including the base **version**, and on
   success the status shows **Saved** and the base version advances.
3. **Given** no actual change (text equals server text), **then** no save request
   is sent.
4. **Given** a save is in flight and the user types more, **then** edits are not
   lost: the client coalesces and flushes again after the in-flight save
   resolves (single-flight, no overlapping saves).
5. **Given** the user switches to another document with unsaved changes, **then**
   the outgoing document is flushed before the new one loads.
6. **Given** the server returns **409** (version mismatch), **then** the client
   does **not** overwrite blindly; it shows the conflict dialog and offers
   "reload server version" and "keep mine", both of which leave the document in a
   consistent **Saved** state afterward.
7. **Given** the network is offline / a save fails transiently, **then** the
   status shows **Offline/Error**, buffered edits are retained, and the client
   retries with backoff; on reconnect (`online` event) it auto-saves.
8. **Given** retries keep failing past the cap, **then** the client stops auto-
   retrying (no busy loop), stays in **Error**, and offers a manual **Retry**.
9. **Given** unsaved changes, **when** the user navigates away in-app or closes
   the tab, **then** they are warned (router guard / `beforeunload`).
10. **Given** the status changes, **then** it is announced to assistive tech via
    an `aria-live` region; the conflict/leave dialogs are focus-trapped and
    keyboard-operable; "discard my edits" is not the default focus.
11. **Given** `Ctrl/Cmd+S` (if implemented), **then** an immediate flush occurs
    and the browser's native save dialog is suppressed.

## 8. Test plan

> Suite stays under 2 minutes. Spec 13 API is mocked (MSW). Timers are
> controlled with fake timers; no real waiting/backoff in tests.

- **Unit (Vitest + RTL, fake timers):**
  - Autosave state machine: dirty→saving→clean on success; version advances;
    no-op when unchanged; single-flight coalescing of overlapping edits.
  - Debounce: edits within the window collapse into one save; blur / doc-switch
    / `visibilitychange` trigger an immediate flush.
  - Conflict: a mocked 409 sets `conflict`, opens the dialog; "reload" replaces
    editor content with server version + clean; "keep mine" re-saves against the
    new version + clean.
  - Offline/retry: a mocked network failure sets `error`/`offline`, schedules
    backoff (advance fake timers), succeeds on retry; respects the retry cap
    (stops, manual retry works); `online` event triggers a flush.
  - Unsaved guard: router blocker + `beforeunload` handler fire when dirty.
  - `SaveStatusIndicator`: renders correct text per status; `aria-live` present.
- **Integration (Vitest + RTL + MSW):**
  - Type in the editor → MSW receives the replace-content call with the right
    body `{ content, version }` → status becomes Saved and the next save uses
    the new version. Then make MSW return 409 → conflict flow resolves.
- **E2E (Playwright):** one flow — open a seeded doc → edit it → see "Saving…"
  then "Saved" → reload the page → the edit persisted. (Conflict/offline are
  covered in unit tests to keep the browser flow short.)
- **Performance/budget note:** fake timers eliminate real debounce/backoff
  waits; all HTTP is mocked. One short Playwright flow. No real backend or
  network.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, TS strict).
- [ ] No new env vars; tunable constants documented in code/`docs/`.
- [ ] Single-user REST autosave only — no WebSocket/CRDT introduced.
- [ ] shadcn/ui used for the conflict/leave dialogs and status badge.
- [ ] No Overleaf code copied (including document-updater logic).
