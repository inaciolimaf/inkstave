# Spec 64 — Runtime Frontend Resilience (requirements)

## 1. Summary

This spec guarantees the frontend never shows a white screen. It adds a **global
React error boundary** at the app root that renders a friendly fallback (with a
"reload"/"try again" affordance) instead of a blank page when a child throws
during render, and it fills in the **few genuinely missing** loading/empty/error
states on the main data views. An audit of the current code (see §5.3) shows most
views already cover these states; this spec adds only the gaps and locks
everything down with fast Vitest + React Testing Library tests.

## 2. Context & dependencies

- **Depends on:** spec 09 (Vite/React/TS, routing via `createBrowserRouter`,
  shadcn/ui components: `Alert`, `Skeleton`, `Card`, `Button`), and the view
  specs 16 (projects), 17 (file tree), 18 (editor), 24 (pdf preview), 38
  (history), 46 (agent chat).
- **Unlocks:** completes the runtime-safety continuation (61–64): with 61
  (no unhandled API throws on 413) and this spec (no render-time white screens),
  the app degrades gracefully end-to-end.
- **Affected areas:** frontend only (`App.tsx`/`main.tsx`, a new error-boundary
  component, targeted view tweaks), plus Vitest tests.

## 3. Goals

- A React error boundary wraps the app root; when a descendant throws during
  render it renders a friendly fallback (not a blank page) with a recovery
  action, and does not crash the whole document.
- Every listed main view renders a sensible **loading**, **empty**, and **error**
  state; any state confirmed missing in the audit (§5.3) is added.
- Tests prove the boundary fallback renders for a thrown child, and that
  representative views render their empty and error states.

## 4. Non-goals (explicitly out of scope)

- No redesign of existing, already-present loading/empty/error states (no churn
  on views that already cover them).
- No global toast/notification framework changes (`sonner` already exists).
- No per-route `errorElement` wiring unless trivially needed; a single app-root
  boundary is sufficient for "no white screen".
- No backend changes.
- No `react-error-boundary` dependency (use a small hand-rolled class component).

## 5. Detailed requirements

### 5.1 Data model (if any)

None.

### 5.2 Backend / API (if any)

None.

### 5.3 Frontend / UI — current-state audit and required changes

Stack facts: React **19.0.0**; `@tanstack/react-query` (test client uses
`retry:false`); `react-router-dom` v7 via `createBrowserRouter`; shadcn/ui has
`Alert`, `Skeleton`, `Card`, `Button` under
`/home/inacio/Área de trabalho/code/inkstave/frontend/src/components/ui/`.
`react-error-boundary` is **not** installed. There is currently **no error
boundary** anywhere (`App.tsx`, `main.tsx`) and no router `errorElement`.

**5.3.1 Global error boundary (REQUIRED — currently missing).**
Add a hand-rolled class component (React 19), suggested path
`/home/inacio/Área de trabalho/code/inkstave/frontend/src/components/error-boundary.tsx`,
implementing `getDerivedStateFromError` and `componentDidCatch`. On error it
renders a friendly fallback built from existing shadcn primitives (`Card`/`Alert`
+ `Button`) with a short message and a recovery action (a "Reload"/"Try again"
button — e.g. resets boundary state or calls `window.location.reload()`). Wrap the
app root with it in
`/home/inacio/Área de trabalho/code/inkstave/frontend/src/App.tsx` (or `main.tsx`)
so it sits **above** the router/provider tree that can throw. The fallback must
include an identifiable role/text (e.g. `role="alert"` and copy like "Something
went wrong") for testability.

**5.3.2 Per-view loading/empty/error audit.** The following already cover all
three states — **do not modify** them (verify only, optionally add a missing test):

- Projects: `frontend/src/features/projects/project-list-view.tsx`
  (`ProjectListSkeleton`, `ProjectListEmpty`, `ProjectListError` + Retry,
  `ProjectListNoResults`). Complete.
- File tree: `frontend/src/features/file-tree/file-tree-panel.tsx` (Skeleton
  loading, `role="alert"` error + Retry, "No files yet" empty). Complete.
- Editor: `frontend/src/features/editor/editor-pane.tsx` (`EmptyState`,
  `LoadingState`, `ErrorState` with 404 detection, `BinaryNotice`,
  collab-loading). Complete.
- PDF preview: `frontend/src/features/pdf-preview/PreviewPane.tsx` +
  `PreviewEmptyState.tsx` + `PreviewErrorState.tsx` (outcome-aware error,
  compiling, pdf-loading, empty). Complete.
- History diff: `frontend/src/features/history/HistoryDiffView.tsx` (loading,
  error+Retry, binary, too-large, no-changes). Complete (note: the 413 path is
  fixed by **spec 61**, not here).

The following have a **confirmed gap** — fix only the gap:

- **History timeline** (`frontend/src/features/history/HistoryTimeline.tsx`): has
  loading (Skeleton) and error (`role="alert"` + Retry) but **no explicit empty
  state** when a doc has zero versions. Add a minimal empty state (e.g. "No
  versions yet.") rendered when the loaded versions list is empty.
- **Agent panel** (`frontend/src/features/agent/AgentPanel.tsx`): has an empty
  state (example prompts) and an error state (`AgentErrorState`), but the
  transcript-loading state is only **deferred** to `AgentTranscript` with no
  explicit visible loading affordance at the panel level. Add a minimal,
  testable loading indicator (e.g. a `role="status"`/`aria-busy` skeleton or
  "Loading…") shown while `chat.transcriptLoading` is true and there are no
  items yet. Keep it minimal and consistent with the other views.

Do not invent states beyond loading/empty/error for these two; do not touch the
"complete" views except to add tests if one is missing.

### 5.4 Real-time / jobs / external integrations (if any)

None.

### 5.5 Configuration

No new env vars.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently.

- `services/web/frontend/js/shared/components/` — any Overleaf error-boundary /
  generic error component (learn the fallback-UI idea only).
- Overleaf's loading/placeholder components in the editor/project-list React
  trees — learn the empty/loading conventions; do not copy markup.

## 7. Acceptance criteria

1. **Given** a child component that throws during render, **when** it is rendered
   inside the global error boundary, **then** the boundary fallback is shown
   (identifiable via `role="alert"`/known copy) and the test does not surface an
   uncaught render error.
2. **Given** the boundary fallback, **when** it renders, **then** it exposes a
   recovery action (a "Reload"/"Try again" button).
3. **Given** the app root, **when** the tree renders normally, **then** the
   boundary is transparent (children render unchanged — no regression).
4. **Given** the history timeline with an empty versions list, **when** it
   renders, **then** it shows the new empty state ("No versions yet." or similar)
   and not an error.
5. **Given** the history timeline in an error state, **when** it renders, **then**
   it still shows the existing error + Retry (no regression).
6. **Given** the agent panel while the transcript is loading with no items,
   **when** it renders, **then** a visible loading affordance
   (`role="status"`/`aria-busy`/copy) is present.
7. **Given** the agent panel error state, **when** it renders, **then** the
   existing `AgentErrorState` still shows (no regression).
8. **Given** representative "complete" views (projects, editor, pdf-preview),
   **when** forced into empty and error states in tests, **then** each renders its
   empty and error UI (locking current behaviour).

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.

- **Unit (Vitest + React Testing Library):**
  - `frontend/src/components/error-boundary.test.tsx` (new): render the boundary
    around a component that throws (a `Thrower` that throws in render) and assert
    the fallback appears (AC1) and exposes the recovery button (AC2); render it
    around a normal child and assert the child shows (AC3). Suppress expected
    `console.error` noise as needed. Use `renderWithProviders` only if router/query
    context is required; otherwise plain `render`.
  - `frontend/src/features/history/HistoryTimeline.test.tsx` (extend): add a case
    with an empty versions page asserting the new empty state (AC4), and keep/add
    an error-state assertion (AC5). Follow the existing hoisted `vi.mock("./api")`
    pattern already used in the history tests.
  - `frontend/src/features/agent/AgentPanel.test.tsx` (new or extend): mock the
    agent chat hook/state so `transcriptLoading` is true with no items and assert
    the loading affordance (AC6); mock an error state and assert `AgentErrorState`
    (AC7). Mirror the mocking style of existing agent tests.
  - Representative "complete" views (AC8): extend or add focused tests
    (`projects-page.test.tsx`, `editor-pane.test.tsx`,
    `pdf-preview/PreviewStates.test.tsx`) to assert empty + error rendering where
    a test does not already exist. Reuse `renderWithProviders` and the global
    `fetch` stub / module-mock patterns already in those folders.
- **Integration:** none (frontend-only spec).
- **E2E (Playwright):** none (fast tier only).
- **Performance/budget note:** All tests are jsdom component renders with mocked
  data — no real network, LLM, or compile. The error-boundary test renders a
  trivial throwing component. Negligible time added.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (global error boundary at app root; the
      two confirmed missing states — history-timeline empty, agent loading).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes (measure with `just test-timed`).
- [ ] Lint/format/type-check clean (ESLint/Prettier, `tsc`).
- [ ] No new dependency added (boundary is hand-rolled); no new env vars.
- [ ] No Overleaf code copied.
