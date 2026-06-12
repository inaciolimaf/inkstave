# Spec 87 — Fix-pack: editor workspace, file-tree, history & schema gaps (requirements)

## 1. Summary

This fix-pack closes ten confirmed issues in and around the editor workspace,
found by two independent reviewers. The set spans four MAJORs — viewer
read-only gating of the file tree (spec 34), an interactive upload-conflict
prompt (spec 17), flush-before-compile reconciliation (spec 31), and optimistic
history-label creation with rollback (spec 38) — plus minors and nits: a
restore-label schema validation gap (spec 37), the Agent toolbar toggle
(spec 46), a global NotificationsBell placement (spec 39), an extracted
`ProjectsHeader` (spec 16), a problems/log tab-vs-stack layout (spec 27), and a
dead font-size clamp/test (spec 60). Apply each as described, keeping tests
green.

## 2. Files in scope

Edit **only** these files (the exact `payload.files` set). Do not touch any file
outside this list — other fix-packs may be running in parallel on other files.

- `backend/src/inkstave/schemas/history.py`
- `frontend/src/features/editor/editor-workspace.tsx`
- `frontend/src/features/editor/use-editor-settings.test.ts`
- `frontend/src/features/editor/use-editor-settings.ts`
- `frontend/src/features/file-tree/file-tree-panel.tsx`
- `frontend/src/features/history/HistoryLabels.test.tsx`
- `frontend/src/features/history/useHistory.ts`
- `frontend/src/features/pdf-preview/PreviewPane.tsx`
- `frontend/src/features/pdf-preview/hooks/useCompile.ts`
- `frontend/src/features/projects/projects-page.tsx`

Restrict edits: stay within these files. The flush-before-compile fix
(issue 117) must be wired only through `editor-workspace.tsx`, `PreviewPane.tsx`,
and `useCompile.ts` (all in scope); do not modify the `InkstaveWsProvider` /
collab-session source (out of scope) — reuse its existing `flush()` method.

## 3. Issues to fix

### Issue 135 — File tree not gated for viewers / read-only (MAJOR)

- **Source spec:** 34-access-control
- **Severity:** major
- **File(s):** `frontend/src/features/editor/editor-workspace.tsx`,
  `frontend/src/features/file-tree/file-tree-panel.tsx`
- **Problem:** `FileTreePanel` (signature at `file-tree-panel.tsx:85–92`) takes no
  `readOnly`/viewer flag, and `editor-workspace.tsx:206–210` renders it without a
  `readOnly` prop — unlike `EditorPane` (line ~226) which correctly receives
  `readOnly={readOnly}`. The panel unconditionally renders New file / New folder /
  Upload (lines ~368–379) and rename/delete context-menu actions, so viewers see
  all mutation affordances. Spec §5.3 (line 189) requires viewers see no
  file-tree mutation actions; AC10 (262–263) requires mutation controls
  hidden/disabled.
- **Fix to apply:** Add a `readOnly?: boolean` prop to `FileTreePanel`. Pass
  `readOnly={readOnly}` from `editor-workspace.tsx` (using the same `readOnly`
  value already threaded to `EditorPane`). When `readOnly` is true, **hide or
  disable** the New file, New folder, and Upload buttons and the rename/delete
  (and move, if present) context-menu actions. Prefer hiding the create/upload
  toolbar and disabling/omitting the destructive context-menu items.

### Issue 54 — Upload name-conflict shows only a toast, no prompt (MAJOR)

- **Source spec:** 17-file-tree-ui
- **Severity:** major
- **File(s):** `frontend/src/features/file-tree/file-tree-panel.tsx`
- **Problem:** AC #10 / §5.3.5 point 6 require that an upload name conflict
  **prompts the user** (at minimum "Replace or Cancel"). The implementation
  (`file-tree-panel.tsx:259–263`) catches a 409/`name_conflict` error and shows
  only `toast.error('"<name>" already exists')` — no interactive dialog, so the
  user cannot choose to replace or rename. No test covers this path.
- **Fix to apply:** On a `name_conflict` upload error, open a shadcn `AlertDialog`
  offering at least **Replace** (overwrite) and **Cancel**; ideally also a
  "Keep both"/rename option. Wire **Replace** to re-upload with replace/overwrite
  semantics (use the existing upload API's replace/overwrite parameter if one
  exists; if not, the minimal acceptable behaviour is a Replace action that
  re-issues the upload with an overwrite flag). Add a component test (this test
  may live in the existing in-scope test file
  `frontend/src/features/history/HistoryLabels.test.tsx` is **not** appropriate —
  the upload-conflict test belongs with the file-tree test in spec 86's
  `file-tree-upload.test.tsx`, which is out of scope here). Therefore, for **this
  pack**, implement the interactive dialog and verify it via an in-component
  render assertion only if a co-located test already exists in scope; otherwise
  ensure the dialog is reachable and rely on the spec-86 conflict test plus
  manual verification. (See §5 Test plan note.)

### Issue 117 — flush() not called before compile (MAJOR)

- **Source spec:** 31-frontend-yjs-binding
- **Severity:** major
- **File(s):** `frontend/src/features/pdf-preview/PreviewPane.tsx`,
  `frontend/src/features/pdf-preview/hooks/useCompile.ts`,
  `frontend/src/features/editor/editor-workspace.tsx`
- **Problem:** Spec §5.4 (182–184) and AC8 (257) require `await session.flush()`
  to run before triggering a compile, so pending local CRDT updates reach the
  server before the compile materializes the content column. `flush()` exists on
  `InkstaveWsProvider` and is unit-tested in isolation, but is never invoked in
  the compile path: `PreviewPane.tsx:187` passes `onCompile={compile.compile}`
  directly with no flush wrapper, and `editor-workspace.tsx` holds no reference to
  the collab session. The only non-test `flush()` calls are autosave and
  diff-review — not compile.
- **Fix to apply:** Thread the collab session (or a `flush` callback) into the
  compile trigger. Concretely: in `editor-workspace.tsx`, pass the existing
  collab session's `flush` (a `() => Promise<void>`) down to the preview/compile
  layer; wrap the compile trigger so it does `await flush()` (guarded: skip/no-op
  if there is no active session) **before** calling `requestCompile`. Implement
  the wrapping in `PreviewPane.tsx` and/or `useCompile.ts` so that
  `CompileButton.onCompile` resolves the flush first. Do not modify
  `InkstaveWsProvider`; reuse its `flush()`.

### Issue 151 — History label creation is not optimistic / no rollback (MAJOR)

- **Source spec:** 38-history-ui
- **Severity:** major
- **File(s):** `frontend/src/features/history/useHistory.ts`,
  `frontend/src/features/history/HistoryLabels.test.tsx`
- **Problem:** Spec §5.3.4 (104–105), AC6 (169–170) and §8 (194) require that
  adding a label **optimistically shows the new badge, rolling back on error with
  a toast**. The `addLabel` mutation (`useHistory.ts:40–44`) only has
  `onSuccess: invalidate` — no `onMutate` optimistic cache write and no `onError`
  rollback. The badge appears only after the server round-trip. The AC6 test
  (`HistoryLabels.test.tsx:37–43`) only asserts `onAdd` was called.
- **Fix to apply:** Add `onMutate` to `addLabel` that cancels in-flight queries,
  snapshots the relevant versions cache, and optimistically writes the new label
  badge into the selected version's labels (via `queryClient.setQueryData`). Add
  `onError` that restores the snapshot and shows `toast.error(...)`. Keep
  `onSettled`/`onSuccess` invalidation to reconcile with the server. Update
  `HistoryLabels.test.tsx` to assert the badge appears **before** the mutation
  resolves (optimistic) and is rolled back on a simulated error.

### Issue 147 — RestoreRequest.label_name missing min_length=1 (MINOR)

- **Source spec:** 37-history-api
- **Severity:** minor
- **File(s):** `backend/src/inkstave/schemas/history.py`
- **Problem:** Spec §5.1.1 specifies label names as 1–255 chars. `LabelCreate.name`
  correctly uses `Field(min_length=1, max_length=255)` (line 90), but
  `RestoreRequest.label_name` (line 99) is `Field(default=None, max_length=255)`
  with **no** `min_length=1`, so an empty string `""` is accepted and would create
  a label with an empty name on restore.
- **Fix to apply:** Change `RestoreRequest.label_name` to
  `Field(default=None, min_length=1, max_length=255)` so empty-string labels are
  rejected with a 422.

### Issue 186 — Agent toolbar button is one-directional, not a toggle (MINOR)

- **Source spec:** 46-agent-chat-ui
- **Severity:** minor
- **File(s):** `frontend/src/features/editor/editor-workspace.tsx`
- **Problem:** The toolbar Agent button (`editor-workspace.tsx:158–164`) does
  `onClick={() => setAgentOpen(true)}` — it always opens and never closes. Spec
  AC1 (227) names it "the Agent toggle in the toolbar".
- **Fix to apply:** Make the button a real toggle:
  `onClick={() => setAgentOpen((v) => !v)}` so clicking while open closes the
  panel. Reflect the open/closed state on the control (e.g. pressed/aria-pressed
  or active styling) consistent with existing toolbar conventions.

### Issue 159 — NotificationsBell absent from the editor app bar (NIT)

- **Source spec:** 39-notifications-email
- **Severity:** nit
- **File(s):** `frontend/src/features/editor/editor-workspace.tsx`,
  `frontend/src/features/projects/projects-page.tsx`
- **Problem:** `NotificationsBell` is mounted only in `projects-page.tsx:56`;
  `editor-workspace.tsx` has no reference. Spec §5.3 (192) says "NotificationsBell
  in the top app bar", implying it should appear in the editor view too.
- **Fix to apply:** Mount `NotificationsBell` in the editor workspace
  header/toolbar so it is present in the editor view as well as the projects list.
  (Both `projects-page.tsx` and `editor-workspace.tsx` are in scope; you may
  simply add the existing `NotificationsBell` to the editor header — no need to
  extract a shared component, though that is acceptable if kept within these two
  files.)

### Issue 53 — ProjectsHeader not extracted as a named component (NIT)

- **Source spec:** 16-project-dashboard-ui
- **Severity:** nit
- **File(s):** `frontend/src/features/projects/projects-page.tsx`
- **Problem:** Spec §5.3.2 (105) names `ProjectsHeader` as a distinct
  sub-component of `ProjectsPage`, but `projects-page.tsx` inlines the `<h1>`
  "Your projects", search input, sort select, and new-project button directly
  (lines ~54–92). No `ProjectsHeader` component exists.
- **Fix to apply:** Extract a local `ProjectsHeader` component (within
  `projects-page.tsx`) wrapping the `<h1>` "Your projects", the search input, the
  sort select, the new-project button — and the `NotificationsBell` if it belongs
  in the header. Keep behaviour and props identical; this is a structural
  extraction only.

### Issue 104 — Problems/Log rendered as stacked sections, not tabs (NIT)

- **Source spec:** 27-compile-error-annotations
- **Severity:** nit
- **File(s):** `frontend/src/features/pdf-preview/PreviewPane.tsx`
- **Problem:** Spec §5.3 (168–169) prescribes the problems panel as "a tab
  alongside the spec-24 raw-log view". `PreviewPane.tsx:210–226` renders
  `ProblemsPanel` then `LogPanel` as stacked sibling sections, not a tab
  switcher.
- **Fix to apply:** Wrap `ProblemsPanel` and `LogPanel` in a shadcn `Tabs`
  component (Problems tab + Log tab) so the two share one tabbed region, matching
  the spec. Preserve existing behaviour (annotations, log content, collapsing if
  applicable) inside the tabs.

### Issue 255 — Dead font-size clamp + misleading test (NIT)

- **Source spec:** 60-refactor-final
- **Severity:** nit
- **File(s):** `frontend/src/features/editor/use-editor-settings.ts`,
  `frontend/src/features/editor/use-editor-settings.test.ts`
- **Problem:** `use-editor-settings.ts` still exports `MAX_FONT = 24` (line 6) and
  clamps to 24, while the popover offers up to 28px and the server allows 28; the
  local store's `fontSize` field is dead (`use-editor-preferences.ts` reads
  `font_size` from the server and only `lineWrapping` from the local store). The
  test (`use-editor-settings.test.ts:21`) asserts clamping to 24 — a
  behaviourally-irrelevant path that may mislead maintainers. The CHANGELOG
  records this as a deliberately-skipped refactor.
- **Fix to apply:** Remove the dead local `fontSize`/`MAX_FONT` clamp and its
  misleading test assertion, **or** (if removal touches too much) update
  `MAX_FONT` to 28 and the test to assert clamping to 28 to match the server
  clamp. Prefer removing the dead path if it is cleanly excisable without
  affecting `lineWrapping` handling; otherwise align to 28. Keep all other
  `use-editor-settings` tests green.

## 4. Acceptance criteria

1. `FileTreePanel` accepts `readOnly` and, when true, hides/disables New file,
   New folder, Upload, and rename/delete (and move) actions;
   `editor-workspace.tsx` passes `readOnly={readOnly}` to it (issue 135).
2. An upload name conflict opens an interactive AlertDialog with at least Replace
   and Cancel (Replace re-uploads with overwrite semantics) instead of only a
   toast (issue 54).
3. Triggering a compile awaits the collab session's `flush()` (when a session is
   active) before `requestCompile`, wired through `editor-workspace.tsx` →
   `PreviewPane.tsx` / `useCompile.ts`, without modifying `InkstaveWsProvider`
   (issue 117).
4. `addLabel` has `onMutate` optimistic cache write + `onError` rollback with a
   toast; a test asserts the badge appears before the mutation resolves and is
   rolled back on error (issue 151).
5. `RestoreRequest.label_name` rejects empty strings via
   `Field(min_length=1, max_length=255)` (issue 147).
6. The toolbar Agent button toggles `agentOpen` (opens and closes) and reflects
   state (issue 186).
7. `NotificationsBell` renders in the editor workspace header as well as the
   projects page (issue 159).
8. A `ProjectsHeader` component exists and is used by `ProjectsPage`
   (issue 53).
9. `ProblemsPanel` and `LogPanel` live in a shadcn `Tabs` switcher in
   `PreviewPane` (issue 104).
10. The dead `MAX_FONT=24` clamp is removed (or aligned to 28) and the misleading
    test assertion is removed/updated (issue 255).

## 5. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Existing green:** Run backend pytest and frontend Vitest before and after;
  keep green.
- **New / updated (frontend, Vitest):**
  - Updated `HistoryLabels.test.tsx`: optimistic badge appears before resolution;
    rollback + toast on error (issue 151).
  - Updated `use-editor-settings.test.ts`: remove/replace the 24-clamp assertion
    to match the fix (issue 255).
  - For the file-tree read-only gating (issue 135) and Agent toggle (issue 186):
    add or extend a co-located component test **only if** one already exists in
    the in-scope files; otherwise verify via existing tests plus manual check.
    Note: the dedicated upload-conflict test (issue 54) belongs to spec 86's
    `file-tree-upload.test.tsx` (out of scope here) — implement the dialog and
    rely on that pack's test + manual verification, keeping this pack's files
    disjoint.
- **New / updated (backend, pytest):**
  - Add/extend a schema/integration test asserting `label_name=""` on
    `RestoreRequest` is rejected (422) and a 1-char name is accepted (issue 147),
    if a suitable in-scope test exists; otherwise this is covered by existing
    history-API tests once the constraint is added.
- **Manual/structural verification:** issues 53, 104, 159 are structural/UI; verify
  by inspection and existing render tests.
- **Performance/budget note:** All changes are unit/component-level; compile flush
  is stubbed via the existing mocked session in tests. No real compile/LLM calls.

## 6. Definition of Done

- [ ] All ten issues (135, 54, 117, 151, 147, 186, 159, 53, 104, 255) addressed
      as described in §3.
- [ ] All acceptance criteria in §4 pass.
- [ ] New/updated tests in §5 written and green; existing tests stay green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint/Prettier/`tsc`; `ruff`/`mypy` for the
      schema change).
- [ ] Only files listed in §2 were modified; `InkstaveWsProvider` untouched.
- [ ] No Overleaf code copied.
