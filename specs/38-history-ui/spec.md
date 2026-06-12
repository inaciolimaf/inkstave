# Spec 38 — History UI (requirements)

## 1. Summary

This spec adds a History view to the editor frontend. It presents a timeline/list
of a document's versions (author + relative/absolute timestamp + labels), a diff
viewer that highlights added/removed text between two selected versions or between a
version and the current document, label management (create/list/delete), and a
"Restore this version" action gated behind a confirmation dialog. It consumes the
spec-37 API and uses shadcn/ui components throughout. No new backend work.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 37** — history REST API (versions, updates, diff, restore, labels).
  - **Spec 24** — the editor shell (panels, toolbar, the place where the PDF preview
    lives) into which the History panel is mounted; the established React/shadcn/router
    patterns from spec 09; the typed API client.
- **Unlocks:** completes the user-facing version-history feature for Phase 5.
- **Affected areas:** frontend only (React components, hooks, API client methods,
  routing/panel state), docs (UI ADR if needed).

## 3. Goals

- A **History** entry point in the editor (toolbar button / panel toggle) that opens a
  History view without leaving the project.
- A **versions timeline**: reverse-chronological list of versions, each showing author
  name/avatar-initials, a timestamp (relative with absolute on hover), op summary, and
  any labels; infinite/"load more" pagination via the API's `before`/`has_more`.
- **Selection model**: select a single version (diff vs. current) or a range of two
  versions (diff A↔B), driven by clicking entries.
- A **diff viewer** rendering the API's hunks/segments with added (green) / removed
  (red) / context highlighting, line numbers, and a binary/too-large fallback message.
- **Label management**: show labels inline; allow creating a label on a version
  (editor/owner), and deleting a label, reflecting `403` for viewers by hiding/disabling
  those controls.
- **Restore**: a "Restore this version" button on a selected version that opens a
  shadcn confirmation `AlertDialog`; on confirm it calls the restore API, shows progress,
  then surfaces success (new version appears at the top) or an error toast.
- Proper loading / empty / error states and keyboard accessibility.

## 4. Non-goals (explicitly out of scope)

- Any new backend endpoints or changes to spec 36/37.
- Real-time/live updating of the history list (a manual refresh + post-restore refetch
  is enough; no WebSocket subscription for history here).
- A frontend diff *algorithm* — diffs come from the API.
- Project-wide history browsing UI beyond what a single document needs; project-level
  label create/restore controls MAY be surfaced minimally but are optional and, if
  shown, only call existing spec-37 project endpoints.

## 5. Detailed requirements

### 5.1 Data model

None (frontend-only spec).

### 5.2 Backend / API

None new. The frontend calls these existing spec-37 endpoints via the typed API client:
- `GET …/docs/{docId}/history/versions?before=&limit=`
- `GET …/docs/{docId}/history/diff?from=&to=`
- `POST …/docs/{docId}/history/restore`
- `GET/POST/DELETE …/docs/{docId}/history/labels[/{id}]`

Add typed client methods + TypeScript types mirroring the spec-37 response schemas.

### 5.3 Frontend / UI

Build under the established frontend feature layout (e.g.
`frontend/src/features/history/`). Use shadcn/ui primitives; no bespoke CSS where a
shadcn component exists.

#### 5.3.1 Entry point & layout
- A **History** toggle in the editor toolbar (icon `History`/clock) opens a History
  panel/overlay (shadcn `Sheet` or a right-side panel consistent with spec 24's layout).
- The panel has two regions: a left **timeline** (version list) and a right **diff /
  detail** region.

#### 5.3.2 Versions timeline (`HistoryTimeline`)
- Fetches page 1 on open; renders each version as a row: author initials/name,
  timestamp (shadcn `Tooltip` shows the absolute ISO time on hover over a relative
  "2 hours ago"), `op_count` summary, and label `Badge`s.
- A **Load more** button (or intersection-observer) requests the next page using
  `next_before` while `has_more`.
- Clicking a row selects it. Shift/modifier-click (or an explicit "compare" affordance)
  selects a second version to define a range. The current selection is visually marked.
- Empty state: "No history yet" when the doc has no versions.

#### 5.3.3 Diff viewer (`HistoryDiffView`)
- Given the current selection, fetches `…/history/diff?from=…&to=…|current` and renders:
  - For each hunk: a header (`@@ -old +new @@`-style or a friendlier label) and the
    ordered segments. `added` segments use a green background, `removed` red, `context`
    neutral, with a left gutter marker (`+` / `-` / ` `).
  - Word-level segments (if the API split them) render inline within a line.
  - Line numbers for old/new sides.
- Fallbacks: `binary: true` → "This document has no text diff." ; `too_large` (413) →
  "This version is too large to diff."
- Loading skeleton while fetching; error state with a retry button.

#### 5.3.4 Labels (`HistoryLabels` / inline)
- Labels appear as badges on their version row and in the detail header.
- An "Add label" control (visible only to editor/owner) opens a small shadcn `Popover`/
  `Dialog` with a name input; submitting calls the create-label API and optimistically
  shows the new badge (rolling back on error with a toast).
- Each label badge for editor/owner shows a delete affordance (× / context menu) calling
  the delete-label API.
- Capability is derived from the project membership/role already available in the editor
  context (spec 33/34); viewers do not see add/delete controls.

#### 5.3.5 Restore (`RestoreVersionButton` + confirm dialog)
- On a selected version, a **Restore this version** button (editor/owner only) opens a
  shadcn `AlertDialog`: title "Restore version N?", body explaining that the current
  content will be replaced and that **a new version is created — nothing is deleted**,
  with an optional "Add a label for this restore" input.
- On confirm: button shows a spinner, calls `POST …/history/restore` (with optional
  `label_name`). On success: close dialog, show a success toast ("Restored to version N;
  created version M"), refetch the versions list (the new version appears on top), and
  the live editor (already bound via spec 31) reflects the restored text through the CRDT
  sync — the History UI does not write to the document itself.
- On failure (`403/409/5xx`): keep the dialog open / show an error toast; no optimistic
  document change.

#### 5.3.6 States & accessibility
- All async regions have explicit loading, empty, and error states.
- Dialogs/sheets are keyboard-navigable and focus-trapped (shadcn defaults); the History
  toggle and version rows are reachable by keyboard; added/removed colours are paired with
  text/gutter markers (`+`/`-`) so the diff is not colour-only (a11y).

### 5.4 Real-time / jobs / integrations

- No new WebSocket messages. After a successful restore, the document content updates via
  the existing spec-28/31 CRDT sync (the server applies the restore as an update). The UI
  only refetches the **history list**; it must not attempt to set editor content directly.

### 5.5 Configuration

- No new env vars. The history feature may sit behind the existing frontend feature-flag
  mechanism if one exists; otherwise it is always on for project members.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` for **layout/UX ideas only**. Write your own React/TSX and
> styling.

- `services/web/frontend/js/features/history/components/change-list/` — how a versions
  timeline / change list is laid out (rows, authors, labels).
- `services/web/frontend/js/features/history/components/diff-view/` — how added/removed
  diff highlighting and the diff panel are arranged.
- `services/web/frontend/js/features/history/components/file-tree/` and
  `history-file-tree.tsx` — multi-file history layout ideas (we focus on a single doc).
- `services/web/frontend/js/features/history/hooks/` and `context/` — state/selection
  patterns (single vs. range selection) — approach only.

## 7. Acceptance criteria

1. **Given** a project member in the editor, **when** they click the History toggle,
   **then** the History panel opens showing the versions timeline for the open document.
2. **Given** more versions than one page, **when** the user clicks "Load more", **then**
   the next page is fetched using `next_before` and appended, and the control disappears
   when `has_more` is false.
3. **Given** a version row, **when** the user hovers the timestamp, **then** a tooltip
   shows the absolute ISO time; the row shows author name/initials and any label badges.
4. **Given** a single selected version, **when** the diff loads, **then** the diff viewer
   shows added (green/`+`), removed (red/`-`), and context segments diffing that version
   against current; **given** two selected versions, **then** it diffs A↔B.
5. **Given** the API returns `binary: true` or `413 too_large`, **when** rendering the
   diff, **then** the corresponding fallback message is shown instead of a diff.
6. **Given** an editor/owner, **when** they add a label to a version, **then** it appears
   as a badge optimistically and persists after refetch; **when** they delete it, **then**
   it disappears; **given** a viewer, **then** add/delete controls are not shown.
7. **Given** an editor/owner selects a version and clicks "Restore this version", **then**
   a confirmation dialog appears explaining the non-destructive, new-version behaviour.
8. **Given** the user confirms a restore, **when** it succeeds, **then** a success toast
   shows, the versions list refetches with the new top version, and the dialog closes;
   the UI does not directly mutate editor content.
9. **Given** a restore fails (e.g. `409`), **when** the API rejects, **then** an error is
   surfaced and no optimistic document/history change persists.
10. **Given** keyboard-only navigation, **when** opening History, moving through versions,
    and confirming a restore, **then** all controls are reachable and dialogs trap focus;
    diff meaning is conveyed by markers, not colour alone.

## 8. Test plan

> Keep the suite under 2 minutes. All backend calls are mocked (MSW/fetch stubs) in unit
> tests; the one Playwright flow runs against a stubbed/seeded backend with no real
> compile or CRDT server traffic for history.

- **Unit (Vitest + React Testing Library):**
  - `HistoryTimeline`: renders versions, pagination "Load more" appends and hides at end,
    empty state (criteria 1, 2, 3).
  - `HistoryDiffView`: renders added/removed/context segments with correct classes/markers;
    binary and too-large fallbacks (criteria 4, 5).
  - `HistoryLabels`: add/delete optimistic update + rollback on error; controls hidden for
    viewer role (criterion 6).
  - Restore dialog: opens with correct copy, confirm calls the API and on success triggers
    refetch + toast; on error shows error and keeps no optimistic change (criteria 7, 8, 9).
  - A11y: markers present on added/removed segments; focusability assertions (criterion 10).
- **Integration:** covered by the above component tests with a mocked API client (no
  separate backend integration needed for a frontend-only spec).
- **E2E (Playwright):** one flow against a stubbed backend — open editor → open History →
  load more → select a version → see diff → (as editor) restore with confirmation → see the
  new version appear and a success toast. Network responses are stubbed/recorded fixtures so
  the test is deterministic and fast.
- **Performance/budget note:** No real history capture, CRDT, or compile in tests; fixtures
  are small; the single Playwright flow uses stubbed responses to avoid backend round-trips.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint + Prettier, TS strict).
- [ ] UI uses shadcn/ui components; no colour-only diff signalling.
- [ ] Docs updated if a UI ADR was made.
- [ ] No Overleaf code or CSS copied.
