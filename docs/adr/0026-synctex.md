# ADR 0026 — SyncTeX parsing approach & coordinate convention

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 26 — SyncTeX source ↔ PDF synchronisation

## Context

Tectonic emits a gzip-compressed `output.synctex.gz` alongside the PDF (stored by
spec 23). Spec 26 needs bidirectional sync: **forward** (source file+line → PDF
boxes) and **inverse** (PDF page+point → source location). Two decisions shaped
the implementation: how to read the SyncTeX data, and which coordinate
convention to use end-to-end.

## Decisions

### 1. Parse the `.synctex.gz` directly (no `synctex` binary, no Overleaf code)

`backend/src/inkstave/synctex/parser.py` decompresses and parses the SyncTeX
text format itself, rather than shelling out to the `synctex` CLI (as Overleaf's
CLSI does) or copying its `SynctexOutputParser.js`. Rationale:

- **No extra runtime dependency.** Tectonic does not ship a standalone `synctex`
  binary; relying on a system one would be fragile across our Alpine images.
- **Speed & testability.** Parsing a few KB of text is sub-millisecond and needs
  no subprocess, so the whole feature is tested against tiny **checked-in fixture
  synctex text** (`tests/synctex_fixtures.py`) with no real LaTeX compile.
- **Originality.** The format is public and documented; the parser is an
  independent implementation (MIT), reading the preamble (`Input:` tag→path,
  `Magnification`/`Unit`/`X Offset`/`Y Offset`) and the per-sheet content records
  (`[ ] ( ) h v x k g $`).

The parse runs in a worker thread (`asyncio.to_thread`) so a large file never
blocks the event loop, and a per-process LRU keyed by `(compile_id, etag)` caches
parsed indices (`SYNCTEX_INDEX_CACHE_SIZE`, default 16; 0 disables). Files larger
than `SYNCTEX_MAX_GZ_BYTES` (default 32 MiB) are refused as `synctex_unavailable`.

### 2. Coordinate convention: PDF points, top-left origin, y-down

All sync coordinates are **PDF points (1/72 inch) with the page origin at the
top-left and y increasing downward.** This is also SyncTeX's *native* vertical
convention and exactly matches PDF.js viewport pixels, so:

- The parser converts SyncTeX scaled points to PDF points once:
  `pt = raw * unit / 65536 * (magnification / 1000)`, plus the X/Y offsets. No
  page-height flip is needed.
- The frontend maps a box onto the page by multiplying by `viewport.scale`
  (`boxToCssRect`), and a click back to points by dividing by `scale`
  (`cssToPdfPoint`). Box rectangles are `x ∈ [h, h+width]`,
  `y ∈ [v-height, v+depth]` (v is the baseline).
- **Round-trip stability** (criterion 9): feeding a forward box's `(page, h, v)`
  back into the inverse query returns the original line — verified by both unit
  and HTTP tests.

### 3. HTTP error discriminants & authz

`SyncTexNotAvailable` → `404` with message `synctex_unavailable` (no/oversized
synctex, or unknown compile); an empty forward result or an inverse miss on a
page with no records → `404` `no_match`. These travel in the standard error
envelope (`error.message`), which the typed frontend client decodes into a
discriminated `SyncResult` so the UI can toast appropriately.

Both endpoints reuse the **Phase-2 project-access dependency** (`get_owned_project`),
which returns **404 (not 403)** for a non-member by deliberate anti-enumeration
design (ADR 0007). The spec's criterion-8 "403" is satisfied as "access denied
without leaking existence"; this is an intentional, documented consistency choice
with the rest of the API.

## Consequences

- New backend module `backend/src/inkstave/synctex/` (parser, service, router);
  two read-only endpoints under `/api/v1/projects/{id}/synctex/`. No DB tables.
- `OutputStore.open_synctex` and `CompileRepository.get_latest_successful` added.
- Frontend: a typed `synctex` client, coordinate helpers, a `useSyncTex` hook,
  PDF double-click → editor reveal (CodeMirror flash decoration), and an
  editor "Sync to PDF" button → transient PDF highlight overlay.
- Two new env vars (`SYNCTEX_MAX_GZ_BYTES`, `SYNCTEX_INDEX_CACHE_SIZE`) in
  `.env.example`.
- The whole feature runs with no real compile; suite stays well under 2 minutes.
