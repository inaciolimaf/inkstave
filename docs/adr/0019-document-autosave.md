# ADR 0019 — Document autosave (single-user REST)

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 19 — Document Autosave (REST)

## Context

Spec 18 shipped a read-only CodeMirror editor. Spec 19 makes it **single-user
editable** and flushes edits to spec 13's **version-checked replace-content**
endpoint over REST — the pre-realtime baseline (Phase 4 replaces it with CRDT
sync). No WebSocket, no multi-user, no OT/CRDT here.

## Decisions

### 1. A client-side autosave state machine

`useDocumentAutosave(projectId, loaded)` owns one document's save lifecycle:
`clean → dirty → saving → clean`, plus `error`, `offline`, `conflict`. It seeds
from spec 18's fetched `{ content, version }` (`baseVersion` / `serverText` /
`localText`), subscribes to the editor's `updateListener` (→ `onLocalChange`),
and flushes the **full content** with the base `version` (spec 13's contract —
not incremental patches).

- **Debounced** (`DEBOUNCE_MS = 1000`) after the last edit; also flushes on
  **blur**, **`visibilitychange` → hidden**, and the **document switch** (the
  outgoing doc is flushed in the seed effect's cleanup). `beforeunload` warns
  (the guard); no `sendBeacon` because the PUT needs a JSON body + auth header.
- **Single-flight + coalesce:** a `savingRef` prevents overlapping saves; edits
  arriving mid-save mark dirty and re-flush on the next tick (so the advanced
  version/serverText have committed first) — no lost edits (AC4).
- **No-op guard:** never saves when `localText === serverText` (AC3).

### 2. Optimistic concurrency & conflict resolution

The save sends `{ content, base_version }`; success advances to the returned
`version`. A **409** is surfaced as `VersionConflictError` carrying the server's
`current_version` + `current_content` (read from the envelope's `error.details`,
which the API client now exposes). The `ConflictDialog` offers:

- **Keep my version** — rebase onto the new server version and re-save local
  (default focus; non-destructive to the user's work).
- **Reload server version** — discard local, load the server content+version
  (not the default focus, since it discards edits — AC10).

Both end in a consistent `clean` state. The client never blind-overwrites.

### 3. Offline / retry with a capped backoff

Transient failures set `error` (or `offline` when `navigator.onLine` is false),
retain buffered edits, and retry with backoff `[1s, 2s, 4s, 8s]`
(`MAX_RETRIES = 4`). Past the cap it **stops auto-retrying** (no busy loop),
stays `error`, and exposes a manual **Retry**. The `window` `online` event
triggers an immediate flush.

### 4. Editable editor & status surface

CodeMirror's read-only facets move into an `editable` **compartment** (spec 18's
view is reused, not recreated); `editable` text does **not** feed back into the
`doc` prop, so the source-of-truth `displayText` only changes on document switch
or conflict reload. A `SaveStatusIndicator` badge (shadcn `Badge`) lives in an
`aria-live="polite"` region. `Ctrl/Cmd+S` forces an immediate flush and
`preventDefault`s the browser dialog.

### 5. Unsaved-changes guard

`UnsavedChangesGuard` (rendered by `EditorWorkspace`, which lives under the data
router) uses React Router's `useBlocker` for in-app navigation + a
`beforeunload` listener for full-page unloads, both active only while dirty. The
dirty flag is lifted from `EditorPane` via `onDirtyChange`.

## Consequences

- New deps: shadcn `badge`, `popover`/`switch` (from spec 18); `ApiError` gained
  a raw `details` field and the API client a `put` method.
- Tunable constants (`DEBOUNCE_MS`, `RETRY_BACKOFF_MS`, `MAX_RETRIES`) live in
  `autosave/types.ts`. No new env vars.
- Phase 4 (28+) replaces this REST sync with CRDT; the dirty/saved UX and the
  conflict concept carry over.

## Alternatives considered

- **Per-keystroke / incremental patches** — rejected; spec 13's contract is a
  full-content versioned replace, and debounced full saves are simpler and
  sufficient single-user.
- **Auto-merge on conflict** — out of scope (Phase 4 / history); reload-or-keep
  is the safe baseline.
- **`sendBeacon` on unload** — can't set the auth header / JSON body cleanly;
  we warn instead and rely on debounce/blur/visibility flushes.
