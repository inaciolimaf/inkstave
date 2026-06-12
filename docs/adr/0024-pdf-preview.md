# ADR 0024 — PDF preview: PDF.js worker bundling & authed PDF fetch

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 24 — PDF Preview UI (PDF.js)

## Context

Spec 24 adds the editor's PDF preview pane: a Compile button driving the spec-22
compile API, a PDF.js viewer for the spec-23 `output.pdf`, and a collapsible raw
log panel. Two integration points needed a deliberate choice: how PDF.js's web
worker is bundled under Vite, and how the PDF bytes are fetched given our
in-memory access token.

## Decisions

### 1. PDF.js worker via Vite `?url` asset import

`pdfjs-dist` needs a web worker. Rather than copying the worker file into
`public/` or pinning a CDN URL (which drifts from the installed version and adds
a third-party dependency at runtime), we import it as a build emitted asset:

```ts
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;
```

Vite hashes and emits the worker as part of the bundle, and the URL always
matches the installed `pdfjs-dist` version. This lives in one wrapper module,
`features/pdf-preview/pdfjs/index.ts`; nothing else imports `pdfjs-dist`
directly. Tests mock that wrapper, so the heavy (and jsdom-unfriendly) library
and its `?url` import never load under Vitest.

### 2. Fetch PDF bytes through the authed API client (not a range URL)

Spec 23 serves `output.pdf` with HTTP range support, and letting PDF.js fetch the
URL directly would use ranges for free. But our access token lives **in memory**
(see ADR 0008) and is sent as an `Authorization: Bearer` header — PDF.js's
internal range fetcher cannot carry it. Wiring a custom authed transport into
PDF.js is fragile, so we fetch the **full bytes** through the existing API client
(`apiClient.getBytes`, which shares the Bearer-injection + refresh-on-401 path)
and hand PDF.js an `ArrayBuffer`. Compiled PDFs for a single document are small;
the simplicity and correct auth outweigh losing range streaming. Range serving
stays available on the backend for future use (e.g. a cookie-auth transport).

### 3. Live status over SSE with a polling fallback

`useCompile` subscribes to the spec-22 SSE `…/events` stream via `EventSource`,
passing the token as an `?access_token=` query param (EventSource cannot set
headers). If `EventSource` is unavailable or the stream errors before a terminal
status, it falls back to polling `GET …/compile/{id}` every
`VITE_COMPILE_POLL_INTERVAL_MS` (default 1000 ms).

## Consequences

- One new dependency: `pdfjs-dist`. The worker is bundled, not external.
- The whole feature is frontend-only and fully mockable; the Vitest suite needs
  no real backend, compile, or network and adds ~1 s to the run.
- If large PDFs ever make full-buffer fetching costly, revisit range streaming
  with a cookie-based or query-token transport so PDF.js can fetch the URL.
