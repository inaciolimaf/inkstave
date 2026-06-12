# Spec 24 — PDF Preview UI (PDF.js) (requirements)

## 1. Summary

This spec adds the **PDF preview pane** to the editor. It introduces a **Compile**
button that triggers the spec-22 compile API, shows the compile moving through
queued → running (with progress/spinner) via the spec-22 status stream/poll,
renders the resulting PDF (fetched from spec 23) using **PDF.js** with **zoom and
page navigation**, and provides a **collapsible log panel** showing the raw
compile output. It defines a clear **error state** when a compile fails. No
clickable SyncTeX (spec 26) and no parsed inline annotations (spec 27).

## 2. Context & dependencies

- **Depends on:**
  - **Spec 18** — the CodeMirror editor UI and the editor page layout into which
    the preview pane is added (split view).
  - **Spec 22** — compile API: `POST …/compile`, `GET …/compile/{id}`, the SSE
    `…/events` stream, and `cancel`.
  - **Spec 23** — output endpoints: `GET …/output.pdf` (range-capable) and
    `GET …/output.log`, plus `…/outputs`.
  - **Spec 09** — frontend foundation: Vite/React/TS/Tailwind/shadcn, the typed
    API client, auth, and the test setup (Vitest + RTL).
- **Unlocks:**
  - **Spec 26** — clickable SyncTeX builds on this pane and the PDF.js viewer.
  - **Spec 27** — inline error annotations build on the parsed log; this spec
    only shows the raw log.
- **Affected areas:** frontend only
  (`frontend/src/features/pdf-preview/…`), plus typed API client additions and
  PDF.js dependency/worker setup. No backend changes.

## 3. Goals

- A **Compile** button that calls spec 22 and reflects state
  (idle / queued / running / success / failure / timeout / cancelled).
- Live status via the spec-22 **SSE** stream, with a **polling fallback** if SSE
  is unavailable.
- **PDF.js** rendering of the produced PDF with continuous page rendering, **zoom
  in/out + fit-width/fit-page**, and **page navigation** (prev/next + jump to
  page + current/total indicator).
- A **collapsible raw-log panel** showing `output.log` text (monospace,
  scrollable, copyable).
- A clear **error/empty/loading** UX for every state.
- **Cancel** affordance while compiling.
- Accessible, keyboard-operable controls using shadcn/ui components.

## 4. Non-goals (explicitly out of scope)

- Clickable SyncTeX / source↔PDF jumping — spec 26.
- Parsed, structured log entries and inline editor markers — spec 27 (here the
  log is shown raw).
- Text selection/search inside the PDF beyond what PDF.js gives for free
  (no custom search UI required).
- Print/download polish beyond a basic "download PDF" link (optional).
- Detached/second-window preview (Overleaf has this; out of scope).

## 5. Detailed requirements

### 5.1 Data model

None (frontend-only). State lives in React/component state and a small store
(e.g. Zustand or context, matching whatever spec 09/18 established).

### 5.2 Backend / API

No new endpoints. This spec **consumes**:
- `POST /api/v1/projects/{id}/compile` (spec 22) → `{ compile_id, status, … }`.
- `GET /api/v1/projects/{id}/compile/{compile_id}` (spec 22) → status snapshot.
- `GET /api/v1/projects/{id}/compile/{compile_id}/events` (spec 22, SSE).
- `POST …/compile/{compile_id}/cancel` (spec 22).
- `GET …/compile/{compile_id}/output.pdf` (spec 23, range-capable).
- `GET …/compile/{compile_id}/output.log` (spec 23).

Extend the typed API client (spec 09) with these calls and their TS types
(mirroring the Pydantic schemas).

### 5.3 Frontend / UI

#### 5.3.1 Layout

The editor page (spec 18) becomes a **split view**: editor on the left, a
**PreviewPane** on the right (resizable splitter; collapse/expand the preview).
Persist the split ratio in local storage.

#### 5.3.2 Components (prefer shadcn/ui primitives)

```
frontend/src/features/pdf-preview/
├── PreviewPane.tsx          # container: toolbar + viewer + log panel
├── CompileButton.tsx        # the Compile/Cancel button with status
├── PdfViewer.tsx            # PDF.js canvas/page rendering
├── PdfToolbar.tsx           # zoom, fit, page nav, download
├── LogPanel.tsx             # collapsible raw log viewer
├── PreviewEmptyState.tsx    # "Compile to see a preview"
├── PreviewErrorState.tsx    # failed/timeout/cancelled messaging
├── hooks/
│   ├── useCompile.ts        # trigger + status stream/poll state machine
│   ├── usePdfDocument.ts    # load + manage the PDF.js document
│   └── useCompileLog.ts     # fetch + cache the raw log
└── pdfjs/                   # PDF.js worker setup / wrapper
```

#### 5.3.3 Compile flow & states (`useCompile`)

A small state machine:
- `idle` → user clicks **Compile** → `POST /compile`.
- on 202 → `queued`; subscribe to SSE `…/events` (fallback: poll
  `GET …/compile/{id}` every ~1s).
- `queued` → `running` (show spinner / indeterminate progress; the button shows
  "Compiling…" and becomes **Cancel**).
- terminal:
  - `success` → load `output.pdf` into the viewer; clear error.
  - `failure` → show `PreviewErrorState` ("Compilation failed — see log"),
    auto-open the log panel.
  - `timeout` → error state ("Compilation timed out").
  - `cancelled` → return to a neutral state showing the previous PDF if any.
  - `error` (system) → error state with a retry affordance.
- **Cancel** calls `POST …/cancel`.
- **Debounce on the client too:** disable the Compile button while a compile is
  active; a rapid re-click does nothing (the backend also coalesces, spec 22).

The hook exposes `{ status, compileId, progressLabel, error, compile(),
cancel() }`.

#### 5.3.4 PDF rendering (`usePdfDocument` + `PdfViewer`)

- Use **PDF.js** (`pdfjs-dist`) with its **web worker** configured for Vite
  (record the worker setup approach in `docs/` if non-obvious).
- Load the PDF from `GET …/output.pdf`. Prefer letting PDF.js fetch the URL so it
  can use **HTTP range requests** (spec 23 supports them) for large PDFs; pass
  the auth token (via the API client's fetch/transport) so the request is
  authorized. If range fetching with auth is awkward, fall back to fetching the
  full bytes via the API client and handing PDF.js an `ArrayBuffer` — document
  the choice.
- Render pages to canvas. Support continuous scroll of all pages (or a virtualised
  list for many pages — virtualisation optional but note the page count).
- Re-render at the selected zoom level; debounce zoom re-renders.
- On the **next successful compile**, replace the document smoothly without
  losing the scroll position where reasonable (best-effort).

#### 5.3.5 Toolbar (`PdfToolbar`)

- Zoom out / zoom in / current zoom %, **Fit width** and **Fit page** presets.
- Page navigation: previous / next, "page X of N", jump-to-page input.
- Optional **Download PDF** button (links to `output.pdf`).
- All controls are keyboard-operable and have accessible labels.

#### 5.3.6 Log panel (`LogPanel`)

- Collapsible (shadcn `Collapsible`/`Accordion` or a toggle). Collapsed by
  default on success; **auto-expanded on failure/timeout**.
- Shows the **raw** `output.log` text in a monospace, scrollable region with a
  "Copy" button. Lazy-fetch the log (only when expanded or on failure) via
  `GET …/output.log`.
- A small status line: outcome, duration, exit code (from the compile status).

#### 5.3.7 Empty / error states

- **Empty:** before any compile, `PreviewEmptyState` invites the user to compile.
- **Error:** `PreviewErrorState` with the outcome, a short message, a "View log"
  action (expands the log), and a "Try again" (re-compile) button.

#### 5.3.8 Accessibility & responsiveness

- Buttons have `aria-label`s; the compiling state is announced (`aria-live`
  polite region for status changes). The log region is focusable and scrollable.
- The pane works at narrow widths (the splitter can collapse the editor).

### 5.4 Real-time / jobs / external integrations

- **SSE** subscription to spec-22's `…/events` for live status; **EventSource**
  or a fetch-stream reader. Clean up the subscription on unmount / terminal
  state. Implement a polling fallback used when SSE errors or is disabled.
- No ARQ, no LLM, no WebSocket of its own (collab WS is later specs).

### 5.5 Configuration

- No backend env vars. Frontend config (in the existing Vite config / env):
  - PDF.js worker URL/bundling handled by the build; document the approach.
  - Optional `VITE_COMPILE_POLL_INTERVAL_MS` (default `1000`) for the polling
    fallback. Add to the frontend `.env.example` if one exists from spec 09.

## 6. Overleaf reference (study only — never copy)

> Read for UI structure and behaviour only; write an independent React/PDF.js
> implementation.

- `services/web/frontend/js/features/pdf-preview/components/pdf-preview.tsx`,
  `pdf-preview-pane.tsx`, `pdf-viewer.tsx`, `pdf-js-viewer.tsx` — overall pane
  composition and how PDF.js is wrapped/driven. Inkstave reimplements as
  `PreviewPane`/`PdfViewer`.
- `…/components/pdf-compile-button.tsx` — the compile button and its state
  affordances. Inkstave's `CompileButton`.
- `…/components/pdf-viewer-controls-toolbar.tsx`, `pdf-zoom-buttons.tsx`,
  `pdf-zoom-dropdown.tsx`, `pdf-page-number-control.tsx` — zoom and page-nav
  controls. Inkstave's `PdfToolbar`.
- `…/components/pdf-logs-viewer.tsx`, `pdf-log-entry-raw-content.tsx`,
  `error-logs.tsx` — the log panel and raw-log display. Inkstave's `LogPanel`
  (raw only; structured entries are spec 27).
- `…/hooks/use-compile-triggers.ts`, `use-log-events.ts` — how compiles are
  triggered and status/log events are consumed. Inkstave's `useCompile`.
- `…/components/pdf-preview-error.tsx` — error-state presentation. Inkstave's
  `PreviewErrorState`.

## 7. Acceptance criteria

> All backend calls are mocked in tests (MSW or the API-client mock from spec
> 09). No real compile runs.

1. **Given** the editor page, **when** it loads, **then** a collapsible preview
   pane is visible with an empty state inviting the user to compile.
2. **Given** the empty state, **when** the user clicks **Compile**, **then**
   `POST …/compile` is called once, the button shows a compiling/Cancel state,
   and a queued/running indicator appears.
3. **Given** a mocked status stream that goes queued→running→success and a mocked
   `output.pdf`, **when** the compile completes, **then** the PDF renders in the
   viewer and the compiling indicator clears.
4. **Given** a rendered PDF, **when** the user zooms in/out and uses Fit
   width/Fit page, **then** the rendered scale changes accordingly and the zoom
   indicator updates.
5. **Given** a multi-page PDF, **when** the user uses next/prev and jump-to-page,
   **then** the viewer navigates and "page X of N" updates.
6. **Given** a mocked status that ends in `failure`, **when** the compile
   finishes, **then** the error state shows, the log panel auto-expands, and
   `GET …/output.log` is fetched and its raw text displayed.
7. **Given** a mocked `timeout` outcome, **when** it finishes, **then** a
   timeout-specific message is shown and a "Try again" action re-triggers a
   compile.
8. **Given** an active compile, **when** the user clicks **Cancel**, **then**
   `POST …/cancel` is called and the UI returns to a neutral/cancelled state.
9. **Given** an active compile, **when** the user clicks Compile again, **then**
   no second `POST …/compile` is fired (client debounce; button disabled).
10. **Given** SSE is unavailable (mock EventSource failure), **when** a compile
    runs, **then** the UI falls back to polling `GET …/compile/{id}` and still
    reaches the terminal state.
11. **Given** the compiling state changes, **then** an `aria-live` region
    announces the new status (accessibility).
12. **Given** a successful re-compile, **when** the new PDF loads, **then** the
    previous PDF is replaced without leaving a stale/broken canvas.

## 8. Test plan

> Frontend-only. Mock all HTTP (MSW or the spec-09 API-client mock). Mock the SSE
> `EventSource`. For PDF.js, either stub the `pdfjs-dist` module (assert it is
> invoked with the right source and that pages/zoom are driven) or load a tiny
> fixture PDF; do not depend on a real backend.

- **Unit (Vitest + RTL):**
  - `useCompile` state machine: idle→queued→running→success/failure/timeout/
    cancelled transitions driven by mocked events; debounce (no double POST);
    cancel; SSE-failure → polling fallback.
  - `CompileButton` renders the right label/affordance per state and disables
    appropriately.
  - `PdfToolbar` zoom/page-nav handlers update state and call the viewer API;
    accessible labels present.
  - `LogPanel` collapses/expands, lazy-fetches the log, auto-expands on failure,
    copy works.
  - `PreviewErrorState`/`PreviewEmptyState` render the correct content per
    outcome.
  - PDF.js wrapper (`usePdfDocument`): with `pdfjs-dist` mocked, asserts the
    document is loaded from the right URL/buffer and re-rendered on zoom change.
- **Integration (Vitest + RTL, component-level with MSW):**
  - Full happy path: click Compile → mocked stream → PDF appears (PDF.js mocked
    or fixture) → zoom/page nav work.
  - Failure path: failure outcome → error state + raw log shown.
- **E2E (Playwright):** a single thin happy-path flow MAY be added (open editor →
  Compile → see preview) but it MUST run against a **mocked/stubbed compile**
  (intercept the compile + output routes; no real Tectonic) so it stays in the
  fast budget. Not strictly required if integration coverage is sufficient.
- **Performance/budget note:** no real compiles, no real network, PDF.js mocked
  or tiny fixture. SSE is mocked and resolved synchronously in tests.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (preview pane, compile button, PDF.js
      viewer with zoom/page-nav, collapsible raw-log panel, error/empty states,
      cancel, SSE+polling).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; no real compiles/network.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ESLint, Prettier, TS strict).
- [ ] PDF.js worker/bundling approach documented in `docs/` if non-trivial.
- [ ] Typed API client extended with the compile/output calls.
- [ ] No Overleaf code copied.
