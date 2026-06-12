# ADR 0017 — File-tree UI: DnD, ARIA tree, optimistic mutations

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 17 — File Tree UI

## Context

The in-editor file tree (left pane of `/projects/:projectId`) renders the spec-12
hierarchy and supports create/rename/move/delete plus binary upload (spec 14). It
must be a keyboard-accessible ARIA `tree`, support drag-and-drop reparenting, and
update optimistically.

## Decisions

### 1. Drag-and-drop: native HTML5, no library

Reparenting uses the **native HTML5 drag-and-drop API** (`draggable`,
`onDragStart/onDragOver/onDrop`) wrapped in the panel's handlers — **no DnD
dependency** (`@dnd-kit` etc.). The interaction is simple (drag an item onto a
folder or the root area; no sibling reordering), so a library isn't warranted.
The dragged id is held in React state; only folders and the root are drop
targets; a `isSelfOrDescendant` guard rejects dropping a folder into itself or a
descendant (no-op + toast).

Because native HTML5 DnD has no built-in keyboard equivalent, **move is also
achievable without a pointer** via the row/context menu **“Move to root”** (and
new items can be created into any folder via its menu). This satisfies the
accessibility requirement without a heavyweight keyboard-DnD library.

### 2. ARIA `tree` with roving tabindex

The container is `role="tree"`; rows are `role="treeitem"` with `aria-level`,
`aria-expanded` (folders), `aria-selected`, nested `role="group"` for children.
Exactly one row is tabbable (**roving tabindex**); the panel's keydown handler
implements `↑/↓` (move), `→/←` (expand-into / collapse-to-parent), `Enter`
(activate: select doc / toggle folder), `F2` (rename), `Delete` (confirm),
`Home/End`, and single-character **type-ahead**. Programmatic `.focus()` moves
focus regardless of tabindex.

### 3. Server state via TanStack Query, optimistic everywhere

The tree lives under `["project", id, "tree"]`. create/rename/move/delete each
apply an **immutable optimistic cache update** (helpers in `tree-utils.ts`) with
snapshot rollback on error and `invalidateQueries` on settle. Expansion state is
**session-persisted** in `sessionStorage` keyed by project id.

### 4. Upload via XHR for real progress

`uploadFile` uses **`XMLHttpRequest`** (not `fetch`) so per-file byte progress
(`upload.onprogress`) drives a `Progress` bar; the access token is read from the
in-memory `tokenStore`. A 409 surfaces as a "already exists" toast (overwrite is
out of scope per spec 14). Everything else (tree CRUD) goes through the shared
`apiClient`.

### 5. Inline rename focus timing

Starting a rename is **deferred a tick** (`setTimeout(0)`) so an open
dropdown/context menu finishes closing and releases focus before the inline
input mounts and autofocuses — otherwise the menu's close-focus management blurs
it instantly (which would commit/cancel immediately). Menus also set
`onCloseAutoFocus` → `preventDefault`.

## Consequences

- No new runtime DnD/tree dependency; added shadcn primitives `tooltip`,
  `progress`, `context-menu` (Radix, MIT). All menus/dialogs/inputs are shadcn.
- The editor (spec 18) consumes the selected doc via `onSelectEntity` (id + type);
  the panel emits on activation of a `doc`/`file`, not folders.
- Tests: tree-building/guards are pure-unit; the panel is integration-tested
  against a stateful `fetch` mock (DnD via `fireEvent.drop`, upload via a mocked
  `uploadFile`); one Playwright flow exercises create/rename/move/upload/delete.

## Alternatives considered

- **`@dnd-kit/core`** (MIT) — richer keyboard DnD, but heavier than this simple
  reparent-only interaction needs; the menu "Move to…" covers keyboard moves.
- **`fetch` for upload** — no byte-level progress; rejected in favour of XHR.
- **Flat normalized store** — the spec-12 API already returns a nested tree;
  we map it to camelCase nodes and derive a flat visible-list for keyboard nav
  rather than maintaining a separate normalized map.
