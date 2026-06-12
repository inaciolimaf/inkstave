# Spec 18 — Editor UI (CodeMirror 6) (requirements)

## 1. Summary

This spec delivers the **CodeMirror 6 editor pane** and the **3-pane IDE shell**
(file tree | editor | preview placeholder) inside `/projects/:projectId`. When a
document is selected in the file tree (spec 17), its content and version are
loaded from the spec 13 API and rendered in a CodeMirror 6 view with **LaTeX
syntax highlighting**, line numbers, a theme, and a few basic editor settings
(font size, keymap, line wrapping). The editor is **read-only** at this stage;
editing and autosave arrive in spec 19. LaTeX highlighting must come from an
independently-licensed (MIT/permissive) CM6 language package — **not** Overleaf's
`lezer-latex` grammar.

## 2. Context & dependencies

- **Depends on:**
  - **17** — file tree UI that emits the selected document (id, type, name).
  - **13** — document content API: `GET` document content + version.
  - **16/09** — the editor route shell, app providers, API client, TanStack
    Query, toasts.
- **Unlocks:**
  - **19** (autosave) — turns this read-only pane editable and wires saving.
  - **24** (PDF preview) — fills the preview placeholder pane.
  - **27/31/32** (annotations, Yjs binding, presence) — extend this editor.
- **Affected areas:** frontend only.

> **API contract note.** Content/version shapes mirror **spec 13**; if they
> differ, spec 13 is authoritative.

## 3. Goals

- Build the **IDE shell**: a resizable 3-pane layout — left = file tree (spec
  17), center = editor, right = preview placeholder.
- Open the selected document: fetch content + version from spec 13.
- Render content in a CodeMirror 6 `EditorView` with:
  - LaTeX syntax highlighting (permissive language package).
  - Line numbers, active-line highlight, bracket matching.
  - A theme (light + dark, following the app theme).
- Provide basic editor settings: **font size**, **keymap** (default | vim |
  emacs — at minimum default; others optional/flagged), **line wrapping** toggle.
- Read-only mode: the document text cannot be modified in this spec.
- Loading / empty / error states for opening a document.
- Accessibility for the editor region and settings controls.

## 4. Non-goals (explicitly out of scope)

- Editing/saving/autosave/dirty tracking (spec 19).
- Compilation, PDF preview content, SyncTeX, log annotations (Phase 3 / spec 24+).
- Collaboration: Yjs binding, remote cursors, presence (Phase 4).
- Autocomplete of LaTeX commands, snippets, command palette, search/replace UI
  (later/optional; not required to pass this spec).
- Editing **binary** files — selecting a `file` (binary) shows a "not a text
  document" placeholder in the editor pane, not a hex/binary editor.
- Multiple open tabs — a single active document is sufficient this spec (tabs
  may come later; if implemented, keep it minimal and out of acceptance scope).

## 5. Detailed requirements

### 5.1 Data model (if any)

None on the server. Types mirror spec 13:

```ts
// frontend/src/features/editor/types.ts
export interface DocumentContent {
  id: string;           // document id
  name: string;
  content: string;      // full text
  version: number;      // optimistic-concurrency version (used heavily in 19)
}
```

### 5.2 Backend / API (if any)

None added. Consumes spec 13 (§5.4).

### 5.3 Frontend / UI

#### 5.3.1 IDE shell & layout

- Route `/projects/:projectId` (the spec 16 shell) is fleshed out into a 3-pane
  layout:

```
EditorWorkspace
├── ProjectTopBar                 (project name, settings trigger; placeholders for compile etc.)
└── ResizablePanels (shadcn "resizable" / react-resizable-panels, MIT)
    ├── Panel: FileTreePanel      (spec 17)
    ├── Panel: EditorPane         (this spec)
    └── Panel: PreviewPlaceholder (this spec — "Preview coming soon" stub)
```

- Use the shadcn **resizable** component (built on `react-resizable-panels`,
  MIT) for the splitters. Persist pane sizes for the session.
- On narrow viewports the panes collapse to a tabbed/stacked layout
  (tree / editor / preview tabs); the editor is the default.

#### 5.3.2 Editor pane component tree

```
EditorPane
├── EditorPaneHeader              (active doc name + read-only badge)
├── EditorEmptyState              (no document selected)
├── EditorLoading                 (skeleton/spinner while fetching content)
├── EditorError                   (load failed + Retry)
├── BinaryFileNotice              (selected entity is a binary 'file')
├── CodeMirrorEditor              (the CM6 host; read-only)
└── EditorSettingsPopover         (shadcn Popover: font size, keymap, wrap)
```

#### 5.3.3 CodeMirror 6 integration

- A `CodeMirrorEditor` React component owns one `EditorView` for the lifecycle
  of the component, created with a stable mount node ref. Re-create or
  `dispatch` reconfiguration via **compartments** (do not tear down the view on
  every prop change).
- **Extensions (baseline set):**
  - LaTeX language support from a **permissive (MIT/Apache/BSD) package**.
    Acceptable options to evaluate (verify the license at implementation time):
    a maintained `codemirror-lang-latex`-style package, or a `@lezer`-based
    LaTeX grammar that is independently MIT-licensed. **Do not** vendor or
    translate Overleaf's `lezer-latex` grammar. If no suitable package exists,
    fall back to a generic StreamLanguage/simple-mode LaTeX highlighter written
    from scratch (basic commands/comments/math). Record the choice + license in
    `docs/`.
  - `lineNumbers()`, `highlightActiveLine()`, `highlightActiveLineGutter()`,
    `bracketMatching()`, `highlightSpecialChars()`, `drawSelection()`.
  - A theme via a **compartment** that follows the app's light/dark mode.
  - `EditorView.lineWrapping` behind a **compartment** toggled by the wrap
    setting.
  - Font size applied via a theme/`EditorView.theme({ '&': { fontSize } })`
    compartment.
  - Keymap via a **compartment**: default = `defaultKeymap` + `historyKeymap`
    + indentation; optional vim/emacs only if a permissive package is added
    (otherwise ship default-only and note it).
  - **`EditorState.readOnly.of(true)` + `EditorView.editable.of(false)`** —
    enforced this spec. (Spec 19 flips these via the same compartment.)
- All CM6 packages are MIT (the CodeMirror project) — confirm versions are
  pinned and licenses are permissive.

#### 5.3.4 State

- **Server state:** `useQuery(['document', documentId], () => getDocument(id))`,
  enabled only when a text document is selected. Returns
  `{ content, version, name }`.
- **Selection source:** the selected entity comes from spec 17 (prop, shared
  editor store, or route param `?doc=` / `/projects/:pid/:docId`). Define a
  single source of truth (e.g. an `editorStore` / Zustand or context from spec
  16/17). When selection changes to:
  - a **doc** → fetch + open it,
  - a **folder** → ignore (folders aren't opened),
  - a **binary file** → show `BinaryFileNotice`.
- **Local settings state:** `{ fontSize: number; keymap: 'default'|'vim'|'emacs';
  lineWrapping: boolean }`, persisted in `localStorage` (per-user, app-wide).
  Defaults: `fontSize: 14`, `keymap: 'default'`, `lineWrapping: true`.

#### 5.3.5 User interactions

1. **Open a document.** Selecting a text doc in the tree loads and displays it.
   Switching to another doc replaces the content (the view is reconfigured/
   `setState`- d, not recreated).
2. **Read-only.** Typing/paste/cut do nothing (no content mutation, no caret-
   based edits); the user can still move the caret, select text, and copy.
3. **Settings.** Opening the settings popover lets the user change font size
   (e.g. 10–24px stepper/select), keymap, and line wrapping; changes apply live
   to the open editor and persist.
4. **Resize panes.** Dragging the splitters resizes; sizes persist for the
   session. Keyboard resize is supported by the resizable primitive.

#### 5.3.6 Validation

- Minimal. Font size clamped to an allowed range (e.g. 10–24). Settings values
  are constrained by the controls (select/stepper), so free-text validation is
  not needed.

#### 5.3.7 Loading / empty / error states

- **No selection:** `EditorEmptyState` — "Select a file to start editing"
  (with hint to use the tree).
- **Loading content:** `EditorLoading` — skeleton lines or a spinner; no layout
  jump when content arrives.
- **Load error:** `EditorError` — message + **Retry** (refetch). 401 handled by
  the API client. 404 (doc deleted) → message + clears selection.
- **Binary file selected:** `BinaryFileNotice` — "This is a binary file and
  can't be edited here."
- **Empty document:** an empty CM6 view (valid, not an error).

#### 5.3.8 Accessibility

- The editor region has an accessible name (`aria-label="LaTeX editor"`) and is
  reachable in the tab order; the read-only state is exposed (badge + the CM6
  content is non-editable, with an `aria-readonly`/role hint where supported).
- Settings controls (Popover + Select/Stepper/Switch from shadcn) are fully
  keyboard-operable and labelled.
- Color contrast of both themes meets WCAG AA for editor text and gutter.
- The resizable splitters expose proper roles/labels (provided by the
  primitive) and are keyboard-resizable.
- Focus is managed when switching documents (focus stays in/returns to the
  editor region, not lost to `document.body`).

### 5.4 Real-time / jobs / external integrations

Consumes **spec 13** via the spec 09 API client:

| Action | Method & path (spec 13) | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| Get document content | `GET /projects/{pid}/docs/{docId}` (or `/documents/{id}`) | – | `200` `{ content, version, name, … }` | `404`,`403`,`401` |

> Follow spec 13's exact path and response envelope (especially the **version**
> field, which spec 19 depends on). Keep HTTP inside
> `frontend/src/features/editor/api.ts`. No WebSocket, no jobs this spec.

### 5.5 Configuration

- No new env vars.
- New frontend deps (all must be MIT/permissive, pinned): `@codemirror/*`
  packages, the chosen LaTeX language package, `react-resizable-panels` (via
  shadcn resizable), optional keymap packages. Document each + its license in
  `docs/` (an ADR-style note recording the LaTeX-grammar licensing decision is
  required).

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for the **approach only**. Paths verified.
> **The `lezer-latex` grammar must NOT be copied or translated.**

- `services/web/frontend/js/features/source-editor/components/codemirror-editor.tsx`
  and `.../components/codemirror-view.tsx` — how a React component hosts a CM6
  `EditorView` and manages its lifecycle (concept only).
- `services/web/frontend/js/features/source-editor/extensions/` (e.g.
  `line-numbers.ts`, `bracket-matching.ts`, `highlight-active-line.ts`,
  `language.ts`, `keybindings.ts`, `theme.ts` if present) — which extensions a
  LaTeX editor wires up and how they're organised with compartments.
- `services/web/frontend/js/features/source-editor/languages/latex/`
  (`latex-language.ts`, `index.ts`) — how a LaTeX `Language`/highlighting is
  assembled (study the *shape*, write your own using a permissive package).
- `services/web/frontend/js/features/source-editor/lezer-latex/` and its
  `README.md` — **reference for understanding only; DO NOT COPY the grammar**.
  Inkstave uses an independently-licensed package instead.
- `services/web/frontend/js/features/source-editor/themes/` — theme structure.
- `services/web/frontend/js/features/ide-react/` and
  `.../ide-react/editor/` — overall IDE shell composition (tree/editor/preview)
  and how the active document is opened (concept only).

Inkstave differences: shadcn/ui + Tailwind, shadcn resizable panels, TanStack
Query, a permissively-licensed LaTeX grammar (never Overleaf's), and a strict
read-only baseline.

## 7. Acceptance criteria

1. **Given** a project is open, **then** the workspace shows a 3-pane layout
   (file tree | editor | preview placeholder) with draggable splitters whose
   sizes persist for the session.
2. **Given** no document is selected, **then** the editor pane shows the
   "select a file" empty state.
3. **Given** a text document is selected in the tree, **then** its content and
   version are fetched from the spec 13 endpoint and displayed in a CodeMirror 6
   view with line numbers.
4. **Given** a `.tex` document, **then** LaTeX syntax is highlighted (commands,
   comments, math) by a permissively-licensed package — **not** Overleaf's
   grammar (verifiable via the dependency/license note in `docs/`).
5. **Given** a document is open, **then** the editor is **read-only**: typing,
   pasting and cutting do not change the content; selecting and copying work.
6. **Given** the user opens editor settings, **when** they change font size /
   keymap / line wrapping, **then** the change applies live to the open editor
   and persists across reloads (localStorage).
7. **Given** a binary file is selected, **then** the editor pane shows the
   "binary file can't be edited here" notice (no CM6 content load).
8. **Given** the content fetch fails, **then** the editor shows an error state
   with a working **Retry**; a 404 clears the selection with a message.
9. **Given** the user switches from doc A to doc B, **then** B's content replaces
   A's by reconfiguring the existing `EditorView` (the view is not torn down and
   recreated on every keystroke/prop change — verifiable via a stable view
   instance/compartment dispatch).
10. **Given** the app theme is dark, **then** the editor uses the dark theme with
    AA-contrast text.
11. **Accessibility:** the editor region is labelled and focusable, the read-only
    state is exposed, settings controls are keyboard-operable, and automated
    `axe` checks report no serious/critical violations on the workspace.

## 8. Test plan

> Suite stays under 2 minutes. Spec 13 API is mocked (MSW). CodeMirror runs in
> jsdom for unit tests where feasible; browser-specific behavior goes to one
> Playwright flow.

- **Unit (Vitest + RTL):**
  - `EditorPane` state machine: no-selection→empty, loading→skeleton,
    error→error+Retry, binary→notice, doc→CodeMirror mounted.
  - `CodeMirrorEditor`: mounts an `EditorView` with the given content; is
    read-only (a dispatched user-style input transaction does not change the doc,
    or `editable`/`readOnly` facets are set); reconfigures via compartment when
    settings change (font size / wrapping / keymap) without recreating the view.
  - Settings persistence: changing a setting writes localStorage; reload reads
    defaults from it; font size clamped to range.
  - Selection routing: selecting folder→ignored, doc→fetch, binary→notice.
  - LaTeX highlighting smoke test: the language extension is present in the
    editor state (extension wired), and the package source/license is the
    permissive one (assert via the configured import, not Overleaf's path).
- **Integration (Vitest + RTL + MSW):**
  - Select a doc from a mocked tree → MSW serves content+version → editor shows
    the text and the version is captured (for spec 19). Switch docs → content
    swaps. Assert the correct spec-13 method/path called.
- **E2E (Playwright):** one flow — open a seeded project → click `main.tex` in
  the tree → editor shows its content with highlighting and line numbers →
  attempt to type (no change, read-only) → open settings, increase font size →
  observe it applied. Single short spec.
- **Performance/budget note:** no real backend; content fetched from MSW. CM6
  setup is fast. Keep CM6 packages tree-shaken; one Playwright flow only.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, TS strict).
- [ ] LaTeX language package is MIT/permissive; the choice + license is recorded
      in `docs/`; **no Overleaf `lezer-latex` grammar copied or translated**.
- [ ] shadcn/ui used for settings popover/controls and the resizable panes.
- [ ] No other Overleaf code copied.
