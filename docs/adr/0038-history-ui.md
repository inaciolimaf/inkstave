# ADR 0038 — History UI: panel, selection model, restore-via-CRDT

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 38 — History UI (timeline, diff viewer, restore)

## Context

Spec 37 exposes version history over REST. Spec 38 is a frontend-only feature that
surfaces it in the editor: a versions timeline, a diff viewer, label management,
and restore. No backend changes.

## Decisions

### 1. A right-side `Sheet`, opened from the editor toolbar

The History view is a shadcn **`Sheet`** (added as `components/ui/sheet.tsx`, a thin
radix-dialog wrapper), opened by a `History` toolbar button next to **Share**. The
sheet holds two regions: a left **timeline** and a right **diff/detail**. The button
is disabled unless a document is open, and the panel is keyed to the open doc's id;
selection resets when the doc changes. This keeps the user in the project (no
navigation) and reuses the spec-24 editor shell.

### 2. Selection model: single = vs-current, range = A↔B

Clicking a version selects it as the **primary** (diff `from=primary, to=current`).
Shift-clicking a second version sets a **compare** version (diff `from=min,
to=max`). A plain click resets the compare. The diff endpoint is only called once a
selection exists, via React Query keyed on `(projectId, docId, from, to)`.

### 3. The diff is rendered, never computed

The frontend renders exactly the hunks/segments the spec-37 API returns: `added`
(green), `removed` (red), `context` (neutral) — each line carries a **gutter marker
(`+`/`-`/` `)** and old/new line numbers, so meaning is never colour-only (a11y).
`binary: true` and `too_large` (413) map to fallback messages; loading shows a
skeleton and errors offer a retry. No diff algorithm lives in the client.

### 4. Restore is confirmation-gated and does not touch the editor

`RestoreVersionButton` (editor/owner only) opens a shadcn `AlertDialog` explaining
the **non-destructive, new-version** behaviour, with an optional restore label.
Confirm calls `POST …/history/restore`; the `AlertDialogAction` `preventDefault`s so
the dialog stays open on failure (error toast, no optimistic change) and closes only
on success (success toast + versions refetch). Crucially, **the UI never writes
editor content** — the server applies the restore as a CRDT update, and the open
editor converges through the existing spec-31 sync. The History panel only refetches
the versions list.

### 5. Capability gating from existing permissions

Add-label, delete-label, and restore controls are shown only when the spec-34
`usePermissions(projectId)` hook reports `doc_write`. Viewers see a read-only
timeline + diff. The server remains the real boundary (403/404 are still handled).

## Consequences

- New `frontend/src/features/history/` (`api`, `types`, `useHistory`, `format`,
  `HistoryTimeline`, `HistoryDiffView`, `HistoryLabels`, `RestoreVersionButton`,
  `HistoryPanel`) + a shadcn `Sheet` component. Wired into `EditorWorkspace`'s
  toolbar. No new env vars.
- Pagination uses React Query `useInfiniteQuery` over the API's
  `before`/`has_more`/`next_before`. Relative timestamps use `Intl.RelativeTimeFormat`
  with the absolute ISO time in a tooltip.
- Tested with Vitest + a mocked API (15 component tests across timeline/diff/labels/
  restore) plus one stubbed Playwright flow (`e2e/history.spec.ts`); the e2e tier is
  not part of the 2-minute unit budget.
