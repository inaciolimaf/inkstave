# Spec 17 — File Tree UI (requirements)

## 1. Summary

This spec delivers the **in-editor file tree panel**: the left column of the
project workspace. It renders the project's folder/document/file hierarchy from
the spec 12 API, and supports creating folders/documents/files, inline rename,
delete (with confirm), drag-and-drop move (reparenting), a context menu, a
single-selection model, and uploading binary files via multipart (spec 14). It
is keyboard-accessible as an ARIA `tree`. Selecting a document emits a selection
the editor (spec 18) will consume; this spec does not load document content.

## 2. Context & dependencies

- **Depends on:**
  - **16** — the `/projects/:projectId` editor route shell and the dashboard
    that navigates into it; the frontend foundation (shadcn/ui, API client,
    TanStack Query, toasts) it established/uses.
  - **12** — file-tree model & API: the tree fetch, create/rename/move/delete
    endpoints, path semantics and validation rules.
  - **14** — binary file storage: the multipart upload endpoint used here for
    "upload file".
- **Unlocks:**
  - **18** (editor) — consumes the selected-document id/path.
  - **19** (autosave) and the compile/preview specs — operate on tree entities.
- **Affected areas:** frontend only. No backend, collab or infra changes.

> **API contract note.** Endpoint shapes below mirror specs **12** and **14**.
> If their implemented shapes differ, those specs are **authoritative**; adapt
> the client/types here.

## 3. Goals

- Fetch and render the project tree (folders, documents, binary files) for the
  current `:projectId`.
- Expand/collapse folders; persist expansion state for the session.
- Single-selection model with a selected-item highlight.
- Create: new folder, new document (`.tex`-style text doc), new (empty) file.
- Rename: inline editing of a tree item's name with validation.
- Delete: with a confirmation dialog (folders warn about contained items).
- Move: drag-and-drop to reparent an item into a folder (or to root).
- Context menu (right-click and a per-row "⋯" button) with the above actions.
- Upload a binary file via multipart to the spec 14 endpoint, into the target
  folder, with progress and conflict handling.
- Full keyboard navigation and screen-reader support (ARIA tree pattern).
- Optimistic updates with rollback + toasts for all mutations.

## 4. Non-goals (explicitly out of scope)

- Loading/editing/saving document content (specs 18–19).
- Previewing binary files (images/PDFs) in the workspace.
- Multi-select / bulk operations (single selection only this spec).
- Folder-level drag *ordering* (sibling reordering); only reparenting is needed.
- Realtime tree updates from other users (Phase 4); the tree refetches/optimist-
  ically updates for the current user only.
- "Linked files", project import, or symlinks.

## 5. Detailed requirements

### 5.1 Data model (if any)

None on the server. TypeScript types mirroring spec 12:

```ts
// frontend/src/features/file-tree/types.ts
export type EntityType = 'folder' | 'doc' | 'file';   // 'file' = binary

export interface TreeEntity {
  id: string;            // uuid
  name: string;
  type: EntityType;
  parentId: string | null;   // null = project root
  // present for type === 'file': size, mimeType, etc. (per spec 14/12)
}

export interface ProjectTree {
  rootId: string | null;       // or a synthetic root; follow spec 12
  entities: TreeEntity[];      // flat list; UI builds the tree
}

// UI-side derived node:
export interface TreeNode extends TreeEntity {
  children: TreeNode[];        // folders only
}
```

> Whether spec 12 returns a **nested** tree or a **flat** list, the UI works
> with a normalized flat map keyed by id and derives the nested `TreeNode`
> structure for rendering. Keep the wire shape behind `api.ts`.

### 5.2 Backend / API (if any)

None added. Consumes spec 12 + spec 14 endpoints (§5.4).

### 5.3 Frontend / UI

#### 5.3.1 Where it lives

- Rendered inside the `EditorPage` shell from spec 16 at `/projects/:projectId`,
  as the **left pane** of the (eventual) 3-pane IDE layout. In this spec the
  middle/right panes may still be placeholders (filled by spec 18); the file
  tree must render and function standalone.
- The tree reads `:projectId` from the route.

#### 5.3.2 Component tree

```
FileTreePanel
├── FileTreeToolbar
│   ├── NewDocButton      (shadcn Button + icon, tooltip "New file")
│   ├── NewFolderButton   (tooltip "New folder")
│   └── UploadButton      (opens hidden <input type=file multiple> / UploadDialog)
├── FileTreeView                       (role="tree", aria-label="Project files")
│   ├── FileTreeSkeleton               (loading)
│   ├── FileTreeError                  (error + Retry)
│   └── FileTreeNode*                  (role="treeitem", recursive for folders)
│       ├── DisclosureToggle           (folders: expand/collapse, aria-expanded)
│       ├── EntityIcon                 (folder/doc/file icon)
│       ├── EntityLabel | InlineRenameInput
│       └── RowMenuButton              (shadcn DropdownMenu "⋯")
├── FileTreeContextMenu                (shadcn ContextMenu wrapping the tree)
├── CreateEntityDialog                 (optional: name prompt for new doc/folder)
├── RenameInline                       (in-row input; no dialog)
├── DeleteEntityDialog                 (shadcn AlertDialog, destructive)
├── UploadDialog / UploadProgressList  (progress per file, conflict prompts)
└── DragLayer / drop indicators        (DnD visual feedback)
```

- **Drag-and-drop:** use a lightweight, MIT-licensed DnD approach. Preferred:
  the native HTML5 drag-and-drop API wrapped in small hooks (no heavy dep), OR
  `@dnd-kit/core` (MIT) if richer keyboard DnD is wanted. Do **not** pull in a
  library outside permissive licensing. Whichever is chosen, note it in `docs/`.
- Menus/dialogs use shadcn `DropdownMenu`, `ContextMenu`, `AlertDialog`,
  `Dialog`, `Input`, `Tooltip`, `Button`, `Progress`, `Skeleton`.

#### 5.3.3 State

- **Server state (TanStack Query):** `useQuery(['project', projectId, 'tree'])`.
  Mutations: `createEntity`, `renameEntity`, `moveEntity`, `deleteEntity`,
  `uploadFile`, each with optimistic cache updates on `['project', id, 'tree']`
  and rollback on error.
- **Local UI state:**
  - `selectedId: string | null` (single selection)
  - `expandedIds: Set<string>` (session-persisted, e.g. in memory or
    `sessionStorage` keyed by projectId)
  - `renamingId: string | null`
  - `dialog: { type: 'create-doc' | 'create-folder' | 'delete' | 'upload' | null; targetId?: string }`
  - `dragState: { draggingId?: string; dropTargetId?: string | 'root' }`
- **Selection emission:** when a `doc`/`file` is activated (Enter or
  click/double-click per §5.3.5), the panel calls an `onSelectEntity(entity)`
  prop and/or updates a route param / shared editor store. The contract the
  editor (spec 18) consumes: the selected document **id** and **type**. Folders
  toggle expansion instead of emitting a selection.

#### 5.3.4 Props (key components)

```ts
FileTreePanel({ projectId, selectedId, onSelectEntity }:
  { projectId: string;
    selectedId: string | null;
    onSelectEntity: (e: TreeEntity) => void; })

FileTreeNode({ node, depth, selectedId, expandedIds, onToggle, onSelect,
               onStartRename, onContextAction, dndHandlers }: …)
```

#### 5.3.5 User interactions

1. **Select.** Single-click a `doc`/`file` selects it (highlight) and emits
   `onSelectEntity`. Single-click a folder selects it; the disclosure toggle (or
   double-click / Enter on a folder) expands/collapses it.
2. **Create folder / doc / file.** Toolbar buttons or context-menu "New …".
   Target parent = the selected folder (or the parent folder of a selected
   file, or root). A name input (inline new row, or a small dialog) appears with
   a sensible default (e.g. `untitled.tex`, `New folder`). Confirm →
   `POST` create on spec 12. Optimistic insert; toast.
3. **Rename.** Context menu → **Rename**, or `F2`, or slow double-click on the
   label → the label becomes an `InlineRenameInput` (text selected). Enter
   commits → `PATCH`/rename; Esc cancels. Optimistic; toast.
4. **Delete.** Context menu → **Delete** → `DeleteEntityDialog`. For a folder,
   the dialog warns it will delete contained items. Confirm → `DELETE`.
   Optimistic removal; if the deleted item was selected, clear selection; toast.
5. **Move (drag-and-drop).** Drag an item; valid drop targets = folders and the
   root area. Visual drop indicator highlights the target folder. Drop →
   `move`/reparent call (set `parentId`). Disallow dropping a folder into itself
   or a descendant (no-op + subtle feedback). Optimistic reparent; rollback on
   error; toast.
6. **Upload.** Toolbar **Upload** opens a file picker (`multiple`). Files upload
   via multipart to the spec 14 endpoint into the target folder, one request per
   file, with a per-file `Progress` bar. Name conflicts surface a prompt
   ("Replace / Keep both / Skip" — minimal: at least "Replace or Cancel" per
   spec 14's behavior). On success the new file appears in the tree; toast.
7. **Keyboard DnD (if @dnd-kit used):** items are reorderable/moveable by
   keyboard per the library's accessible pattern; otherwise provide a context-
   menu **Move to…** fallback so move is achievable without a pointer.

#### 5.3.6 Validation

- Names: required; trimmed; 1–255 chars; reject all-whitespace; reject path
  separators (`/`, `\`) and names `.`/`..` (paths are derived server-side per
  spec 12). Reject duplicate names within the same parent folder (mirror spec
  12's rule; surface server 409/422 if the client check is bypassed).
- Document/file extensions are not enforced by the UI beyond the default
  suggestion; spec 12 decides what's a `doc` vs `file`.
- Inline validation message appears near the rename/create input; commit is
  blocked while invalid.

#### 5.3.7 Loading / empty / error states

- **Loading:** `FileTreeSkeleton` (a few shimmer rows).
- **Empty:** a project tree always has a root; if root has no children, show a
  subtle "No files yet — create one" hint with quick **New file** / **Upload**
  actions. (Per spec 11/12, projects may be seeded with a `main.tex`; if so,
  empty is rare but still handled.)
- **Error:** `FileTreeError` with **Retry** (refetch). 401 handled by the API
  client (spec 09).
- **Mutation pending:** the affected node shows a pending style; on failure the
  optimistic change rolls back with an error toast.
- **Upload pending:** per-file progress; failed uploads show a retry/dismiss.

#### 5.3.8 Accessibility (ARIA tree pattern)

- Container `role="tree"`, `aria-label="Project files"`; each row
  `role="treeitem"` with `aria-level`, `aria-expanded` (folders),
  `aria-selected`, and `aria-setsize`/`aria-posinset` where practical.
- **Roving tabindex:** exactly one treeitem is tabbable; the rest are reached
  with arrow keys.
- **Keyboard:** `↑/↓` move between visible items; `→` expand (or move into
  first child) / `←` collapse (or move to parent); `Enter` activate (select doc
  / toggle folder); `F2` rename; `Delete` opens delete confirm; `Home`/`End`
  jump to first/last; typing a letter does type-ahead to the next matching name.
- Dialogs/menus use shadcn primitives (focus trap, Esc, focus restore).
- Drag-and-drop has a non-pointer equivalent (keyboard DnD or "Move to…" menu).
- Visible focus rings; selection isn't conveyed by color alone (also
  `aria-selected` + a selected indicator).
- Icons have accessible names or are `aria-hidden` with adjacent text labels.

### 5.4 Real-time / jobs / external integrations

Calls **spec 12** (tree) and **spec 14** (upload) via the spec 09 API client:

| Action | Method & path (spec 12/14) | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| Get tree | `GET /projects/{pid}/tree` | – | `200` tree | `404`,`403`,`401` |
| Create folder | `POST /projects/{pid}/folders` | `{ name, parentId }` | `201` entity | `409`,`422` |
| Create doc | `POST /projects/{pid}/docs` | `{ name, parentId }` | `201` entity | `409`,`422` |
| Create file (empty) | per spec 12 (may be a doc or file create) | `{ name, parentId }` | `201` | `409`,`422` |
| Rename | `PATCH /projects/{pid}/entities/{id}` | `{ name }` | `200` | `404`,`409`,`422` |
| Move | `PATCH /projects/{pid}/entities/{id}` | `{ parentId }` | `200` | `404`,`409`(cycle),`422` |
| Delete | `DELETE /projects/{pid}/entities/{id}` | – | `204` | `404`,`403` |
| Upload binary | `POST /projects/{pid}/files` (multipart) | `file`, `parentId`, `name` | `201` entity | `409`,`413`(too large),`415`,`422` |

> Exact paths/verbs follow specs 12 and 14. Rename and move may be a single
> `PATCH` accepting `name` and/or `parentId`, or separate endpoints — follow
> spec 12. Keep all HTTP in `frontend/src/features/file-tree/api.ts`.

### 5.5 Configuration

- No new env vars. Max upload size / allowed types are enforced by spec 14
  server-side; the UI may read a client constant for friendlier pre-validation
  but must not be the source of truth.
- If a DnD library (`@dnd-kit`) is added, document it in `docs/`.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for the **approach only**. Paths verified.

- `services/web/frontend/js/features/file-tree/` — overall panel structure,
  contexts and hooks organisation.
- `services/web/frontend/js/features/file-tree/components/file-tree-root.tsx`,
  `.../file-tree-folder.tsx`, `.../file-tree-folder-list.tsx`,
  `.../file-tree-doc.tsx` — how the recursive tree, folders and items are
  rendered (study structure, not code).
- `services/web/frontend/js/features/file-tree/components/file-tree-context-menu.tsx`
  and `.../file-tree-item/` — context menu and per-item action UX.
- `services/web/frontend/js/features/file-tree/components/file-tree-create/`
  (e.g. `file-tree-create-name-input.tsx`,
  `file-tree-modal-create-file-body.tsx`, `file-tree-upload-conflicts.tsx`) —
  create/upload flows and conflict-resolution UX.
- `services/web/frontend/js/features/file-tree/components/file-tree-draggable-preview-layer.tsx`
  — drag preview/feedback approach (concept only).

Inkstave differences: shadcn/ui + Tailwind (not Bootstrap), TanStack Query for
server state, native/`@dnd-kit` DnD (not the Overleaf DnD stack), and a strict
ARIA `tree` keyboard model. No code is copied.

## 7. Acceptance criteria

1. **Given** a project with files, **when** the editor route loads, **then** the
   tree renders the folder/doc/file hierarchy from `GET …/tree`.
2. **Given** a folder, **when** the user toggles it, **then** it expands/collapses
   and `aria-expanded` reflects the state; expansion persists for the session.
3. **Given** a doc is clicked/activated, **then** it becomes the selected item
   (highlight + `aria-selected`) and `onSelectEntity` fires with its id/type;
   activating a folder toggles it instead.
4. **Given** **New folder/doc**, **when** a valid name is confirmed, **then** the
   correct create endpoint is called with the right `parentId`, the item appears
   optimistically, and a success toast shows.
5. **Given** an empty/whitespace/duplicate/separator-containing name, **then**
   create/rename is blocked with an inline message; no request is sent (or the
   server 409/422 is surfaced if bypassed).
6. **Given** **Rename** (menu or `F2`), **then** the label becomes an inline
   input; Enter commits via the rename endpoint (optimistic), Esc cancels.
7. **Given** **Delete** on a folder, **then** the confirm dialog warns about
   contained items; confirming calls delete, removes the subtree optimistically,
   clears selection if it was selected, and toasts.
8. **Given** a drag of item A onto folder B, **then** a drop indicator shows on
   B, dropping reparents A (move endpoint, `parentId=B`) optimistically; failure
   rolls back with an error toast.
9. **Given** a drag of a folder onto itself or its descendant, **then** the drop
   is rejected (no move call) with subtle feedback.
10. **Given** **Upload** with a binary file, **then** it is sent as multipart to
    the spec 14 endpoint into the target folder with a visible progress bar; on
    success it appears in the tree; a name conflict prompts the user.
11. **Keyboard:** with focus in the tree, `↑/↓/→/←/Enter/F2/Delete` and
    type-ahead all work per §5.3.8; only one treeitem is in the tab order
    (roving tabindex). Move is achievable without a pointer.
12. **Loading/error:** the tree shows a skeleton while loading and an error
    state with a working **Retry** on fetch failure.
13. **Accessibility:** automated `axe` checks report no serious/critical
    violations; the tree exposes `role="tree"`/`treeitem` with correct
    `aria-level`, `aria-expanded`, `aria-selected`.

## 8. Test plan

> Suite stays under 2 minutes. Spec 12/14 APIs are mocked (MSW); no real
> backend in unit/integration tiers.

- **Unit (Vitest + RTL):**
  - Tree building: flat entities → nested `TreeNode`s; correct ordering
    (folders first / alphabetical per chosen rule).
  - `FileTreeNode`: renders icon/label/disclosure; `aria-*` attributes correct;
    selected/expanded styling.
  - Keyboard model: arrow navigation, expand/collapse, Enter activation, F2
    rename, Delete confirm, roving tabindex, type-ahead.
  - Validation: empty/whitespace/duplicate/`/`-containing names blocked.
  - Create/rename/delete optimistic update + rollback on mocked rejection.
  - DnD guard: dropping a folder into its descendant is a no-op.
  - Upload: builds correct multipart request; progress updates; conflict prompt.
- **Integration (Vitest + RTL + MSW):**
  - Full panel against MSW tree: create doc → appears; rename → updates; move
    (simulate drop) → `parentId` change persisted; delete folder → subtree gone.
    Assert exact method/path/body per spec 12/14 handlers.
- **E2E (Playwright):** one flow — open a seeded project → create a folder →
  create a doc inside it → rename the doc → drag it to root → upload a small
  binary file → delete the folder. Single spec file; small fixtures.
- **Performance/budget note:** all unit/integration use mocked HTTP; the upload
  test uses a tiny in-memory blob. Only one Playwright flow, kept short.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, TS strict).
- [ ] Any new dep (e.g. `@dnd-kit`) is MIT/permissive and documented in `docs/`.
- [ ] shadcn/ui used for menus/dialogs/inputs/progress (no hand-rolled CSS).
- [ ] ARIA `tree` pattern verified (axe clean; keyboard operable).
- [ ] No Overleaf code copied.
