# Spec 26 — SyncTeX source ↔ PDF synchronisation (requirements)

## 1. Summary

This spec adds bidirectional SyncTeX synchronisation between the LaTeX source
and the compiled PDF. Tectonic (spec 21) emits a compressed `.synctex.gz`
alongside the PDF; spec 23 stores it. Here we parse that data to answer two
queries — **forward** (source file + line → PDF page + rectangle) and **inverse**
(PDF page + x/y → source file + line) — expose them as two backend endpoints,
and wire the PDF.js preview and CodeMirror editor so a click in one jumps to /
highlights the other. The SyncTeX file format is public and well documented; we
write our own resolver. Overleaf is consulted only for *how the query results
flow to the viewer*, not for the parser.

## 2. Context & dependencies

- **Depends on:**
  - **spec 23** (output storage): gives us the per-compile artefact set —
    `output.pdf`, `output.log`, and `output.synctex.gz` — addressable by
    `(project_id, compile_id)` or "latest successful compile for project", plus
    the local on-disk path of each artefact while it exists in the output store.
  - **spec 24** (PDF preview UI): gives us a mounted PDF.js viewer component, the
    open editor (CodeMirror 6 from spec 18), knowledge of which document/file is
    open, and the compile trigger.
- **Unlocks:** spec 27 (error annotations) reuses the same "jump to source
  line" plumbing; later collaboration/agent specs benefit from accurate
  source↔PDF mapping but do not require it.
- **Affected areas:** backend (new `synctex` module + 2 endpoints), frontend
  (PDF viewer + editor sync wiring), docs (parser decision ADR).

## 3. Goals

- Parse Tectonic's `.synctex.gz` into an in-memory index usable for both forward
  and inverse queries, without copying Overleaf's parser.
- Backend endpoint **code → pdf** (forward): given file + line (+ optional
  column), return one or more PDF positions (page, rectangle in PDF points).
- Backend endpoint **pdf → code** (inverse): given page + x/y (in PDF points),
  return the best source file + line (+ column when available).
- Frontend: clicking in the PDF preview scrolls the editor to the source line
  and flashes a highlight; clicking (via a sync button or modifier-click) in the
  editor scrolls the PDF to the target and flashes a highlight rectangle.
- Robust handling of: missing/absent synctex data, stale compiles, multi-file
  projects (`\input`/`\include`), and coordinate-system conversion.
- Everything tested with checked-in fixture synctex data so tests need no real
  LaTeX compile and stay well within the 2-minute budget.

## 4. Non-goals (explicitly out of scope)

- Compile-error and warning annotations / problems panel — **spec 27**.
- Running compiles, generating the `.synctex.gz`, or storing it — **specs 21–23**.
- Real-time collaborative cursor sync — Phase 4.
- "Highlight every occurrence" or full-text search-driven sync; only SyncTeX
  geometric mapping is in scope.
- Caching/precomputing the synctex index across requests beyond a simple
  per-process LRU (optional optimisation, see §5.2).

## 5. Detailed requirements

### 5.1 Data model

No new database tables. SyncTeX data lives in the output store (spec 23) as the
compile artefact `output.synctex.gz`. This spec adds **in-memory** models only
(Pydantic v2 / dataclasses), defined in `backend/app/synctex/models.py`:

```python
class SyncTexBox(BaseModel):
    page: int            # 1-based PDF page number
    h: float             # horizontal position, PDF points, origin top-left
    v: float             # vertical position (baseline), PDF points, origin top-left
    width: float         # box width in PDF points (>= 0)
    height: float        # box height in PDF points (>= 0)
    depth: float         # box depth in PDF points (>= 0)

class ForwardResult(BaseModel):
    # code -> pdf: one source line may map to several PDF boxes
    boxes: list[SyncTexBox]

class InverseResult(BaseModel):
    file: str            # project-relative source path, e.g. "main.tex"
    line: int            # 1-based source line
    column: int | None   # 1-based column when SyncTeX provides it, else None
```

Coordinate convention used throughout Inkstave: **PDF points (1/72 inch), origin
at the top-left of the page, y increasing downward.** SyncTeX's native units are
"sp" (scaled points, 65536 sp = 1 TeX pt) with a bottom-left-ish origin defined
by the `Magnification`/`Unit`/`X Offset`/`Y Offset` preamble fields; the parser
MUST convert into the Inkstave convention so the frontend can map straight onto
PDF.js page viewport coordinates.

### 5.2 Backend / API

#### 5.2.1 Parser module — `backend/app/synctex/parser.py`

Implement an independent SyncTeX parser. The `.synctex.gz` is gzip-compressed
text. Approach (documented in `docs/`):

- **Preamble:** read `SyncTeX Version:`, `Input:<tag>:<path>` (maps integer
  *tag* → source file path), `Magnification`, `Unit`, `X Offset`, `Y Offset`.
  Compute the sp→pt and offset conversion once.
- **Content section** (`{`…`}` per page): records of forms
  `[`/`]` (vbox), `(`/`)` (hbox), `h`/`v`/`x`/`k`/`g`/`$` (glue/kern/math/leaf
  nodes). Each record encodes `tag,line[,column]:h,v[:W,H,D]`. Build:
  - a flat list of **leaf boxes** per page, each carrying `(tag, line, column,
    h, v, width, height, depth)` for **inverse** queries;
  - an index keyed by `(file, line)` → list of boxes for **forward** queries.
- Numbers are in sp; convert to pt with the preamble unit, then to top-left
  origin using page height (page height in pt taken from the synctex preamble's
  `Y Offset`/sheet records — or, simpler and acceptable, keep SyncTeX's native
  page-relative coordinates and let the frontend convert using the PDF.js page
  viewport height which it already has). **Document whichever convention you
  pick and keep it consistent between the two endpoints and the frontend.**

Public contract:

```python
class SyncTexIndex:
    @classmethod
    def from_gz_bytes(cls, data: bytes) -> "SyncTexIndex": ...
    @classmethod
    def from_gz_path(cls, path: str | os.PathLike) -> "SyncTexIndex": ...

    def forward(self, file: str, line: int, column: int | None = None
                ) -> ForwardResult:
        """code -> pdf. Returns boxes for the nearest indexed line >= line in
        that file (fall back to nearest line below if none above). Empty boxes
        list if the file is unknown."""

    def inverse(self, page: int, h: float, v: float) -> InverseResult | None:
        """pdf -> code. Returns the source location of the box on `page` whose
        rectangle contains (h, v); if none contains it, the nearest box by
        Euclidean distance of its reference point. None if the page has no
        records."""
```

Implementation notes / contracts:
- `file` matching is by **project-relative path** as recorded in the `Input:`
  lines. Tectonic typically records paths relative to the compile root; the
  resolver MUST normalise (strip a leading `./`, collapse `..`) and match
  case-sensitively. If the requested file is not an `Input`, `forward` returns
  empty boxes (HTTP layer turns this into 404, see below).
- Parsing must be tolerant: unknown record types are skipped; a malformed line
  raises `SyncTexParseError` only if the preamble itself cannot be read.
- Optional: a module-level `functools.lru_cache`-style cache keyed by
  `(compile_id, mtime)` so repeated clicks on the same compile don't re-parse.
  Cap at e.g. 16 entries. Not required for correctness.

#### 5.2.2 Service — `backend/app/synctex/service.py`

```python
class SyncTexService:
    def __init__(self, output_store: OutputStore): ...  # spec 23 dependency

    async def load_index(self, project_id: UUID, compile_id: str | None
                         ) -> SyncTexIndex:
        """Resolve compile_id (None => latest successful), fetch the
        output.synctex.gz bytes from the output store, build/return the index.
        Raises SyncTexNotAvailable if the compile produced no synctex.gz."""

    async def code_to_pdf(self, project_id, compile_id, file, line, column
                         ) -> ForwardResult: ...
    async def pdf_to_code(self, project_id, compile_id, page, h, v
                         ) -> InverseResult: ...
```

#### 5.2.3 HTTP endpoints — `backend/app/synctex/router.py`

Both require an authenticated user (current-user dependency from spec 08) who is
a member of the project (reuse the project-access dependency established in
Phase 2; a collaborator stub is acceptable until spec 34 tightens authz). Mount
under the existing project router prefix.

**Forward — `GET /api/projects/{project_id}/synctex/code-to-pdf`**

Query params:
| param | type | required | notes |
| --- | --- | --- | --- |
| `file` | str | yes | project-relative source path |
| `line` | int ≥ 1 | yes | 1-based source line |
| `column` | int ≥ 1 | no | 1-based; ignored if synctex lacks columns |
| `compile_id` | str | no | defaults to latest successful compile |

Response `200`: `ForwardResult` (JSON `{"boxes": [SyncTexBox, …]}`).
Errors: `404` if project/compile/synctex.gz absent or `file` not an Input;
`422` on invalid params; `401/403` on auth.

**Inverse — `GET /api/projects/{project_id}/synctex/pdf-to-code`**

Query params:
| param | type | required | notes |
| --- | --- | --- | --- |
| `page` | int ≥ 1 | yes | 1-based PDF page |
| `h` | float | yes | horizontal position, PDF points |
| `v` | float | yes | vertical position, PDF points |
| `compile_id` | str | no | defaults to latest successful compile |

Response `200`: `InverseResult` (`{"file","line","column"}`).
Errors: `404` if no synctex.gz or page has no records; `422`/`401`/`403` as above.

The HTTP layer maps `SyncTexNotAvailable` → `404` with body
`{"detail":"synctex_unavailable"}`, and an empty forward result → `404`
`{"detail":"no_match"}` so the frontend can distinguish "no sync data" from "no
match on this line".

### 5.3 Frontend / UI

Add a small typed client and wire it into the spec-24 viewer and spec-18 editor.

- **API client** (`frontend/src/lib/api/synctex.ts`):
  `codeToPdf(projectId, {file, line, column?, compileId?})` and
  `pdfToCode(projectId, {page, h, v, compileId?})` returning the typed results;
  both surface `404 no_match`/`synctex_unavailable` as a discriminated result so
  callers can toast appropriately.
- **Inverse sync (PDF → editor):** in the PDF.js viewer, on click (default
  double-click, configurable) on a page, convert the click point from the page's
  CSS pixel coordinates to PDF points using the page viewport (`viewport.scale`,
  page rotation = 0 assumed), call `pdfToCode`, then:
  - if the target `file` is the open document, scroll the editor to `line` and
    flash a line highlight (CodeMirror decoration, ~1.2s);
  - if it is a *different* file in the project, open that document first (reuse
    the file-tree/editor open flow) then scroll + flash.
- **Forward sync (editor → PDF):** add a "sync to PDF" action — a toolbar button
  and/or a modifier-click in the editor gutter — that takes the current cursor
  line + the open file path, calls `codeToPdf`, then scrolls the PDF.js viewer
  to `boxes[0].page` and renders a transient highlight rectangle over the box
  (converted from PDF points back to viewport pixels), fading after ~1.2s.
- **States:** disable both sync actions when there is no successful compile yet;
  on `synctex_unavailable` show a non-blocking toast "SyncTeX data not available
  for this compile"; on `no_match` show "No matching location". No spinners are
  needed (requests are sub-100ms against fixtures/local files).
- **Accessibility:** the editor "sync to PDF" button is keyboard-focusable with
  an accessible label; highlight flashes must not be the only signal (also move
  scroll position).

Prefer existing shadcn/ui Button/Toast components; do not hand-roll CSS for the
highlight beyond a simple absolutely-positioned, pointer-events-none overlay.

### 5.4 Real-time / jobs / external integrations

None new. Parsing happens synchronously inside the request (it is fast: a few ms
for typical documents). No ARQ job is needed because there is no long-running
work — the `.synctex.gz` already exists from the spec-22 compile job. If a
project's synctex file is large enough to risk blocking the event loop, run the
parse in a thread (`anyio.to_thread.run_sync`); this is the recommended default.

### 5.5 Configuration

- `SYNCTEX_MAX_GZ_BYTES` (default `33554432`, 32 MiB): refuse to parse
  unexpectedly large synctex files; over the limit → `404 synctex_unavailable`
  with a logged warning.
- `SYNCTEX_INDEX_CACHE_SIZE` (default `16`): max parsed indices cached in
  process; `0` disables caching.
- No secrets. Add both to `.env.example` with comments.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently. **Note:** Overleaf shells out to the `synctex` binary
> and parses its `synctex view`/`synctex edit` *text output*; Inkstave parses the
> `.synctex.gz` directly (or may shell to `synctex` if available) — either way,
> write your own resolver.

- `services/clsi/app/js/SynctexOutputParser.js` — how the `synctex` CLI's
  `view`/`edit` stdout is parsed into `{page,h,v,width,height}` and
  `{file,line,column}` records. Learn the field meanings; do **not** copy the
  parser.
- `services/clsi/app/js/CompileManager.js` (the `syncFromCode`/`syncFromPdf`
  paths) — how a forward/inverse request resolves the output directory and
  invokes synctex. Learn the request→artefact resolution flow.
- `services/web/frontend/js/features/pdf-preview/hooks/use-synctex.ts` and
  `.../components/pdf-synctex-controls.tsx`, `.../util/highlights.ts` — how the
  viewer converts viewport coordinates, fires sync requests, and draws highlight
  rectangles, and how forward/inverse buttons are wired. Learn the UX; write
  your own React.

## 7. Acceptance criteria

Given a checked-in fixture `.synctex.gz` (and its `Input:` map) for a known
2-page document:

1. **Forward, same file.** GET `code-to-pdf?file=main.tex&line=10` returns
   `200` with at least one box whose `page` and `v` match the fixture's expected
   value for line 10 (within a documented tolerance, e.g. ±1 pt).
2. **Forward, nearest line.** Requesting a `line` with no exact record returns
   the nearest indexed line's boxes (not an empty list), per §5.2.1.
3. **Forward, unknown file.** GET with `file=does-not-exist.tex` returns `404`
   `{"detail":"no_match"}`.
4. **Inverse, inside a box.** GET `pdf-to-code?page=1&h=H&v=V` for an `(H,V)`
   inside a known box returns `200` with the fixture's expected `file` and
   `line`.
5. **Inverse, nearest.** GET with an `(h,v)` outside all boxes returns the
   nearest box's `file`/`line`, not `404`.
6. **Multi-file mapping.** A fixture with `\input{sections/intro.tex}` returns
   `file="sections/intro.tex"` (project-relative, normalised) for an inverse
   query on that region.
7. **No synctex data.** For a compile whose artefacts lack `output.synctex.gz`,
   both endpoints return `404` `{"detail":"synctex_unavailable"}`.
8. **Auth.** Both endpoints return `401` without a token and `403` for a user
   who is not a project member.
9. **Coordinate convention.** Forward then inverse round-trips: feeding the box
   returned by criterion 1 back into `pdf-to-code` returns the original `line`
   (round-trip stability — documents the chosen coordinate convention).
10. **Frontend inverse.** In an e2e/component test with a stubbed API, clicking a
    page in the PDF viewer scrolls the editor to the returned line and applies a
    highlight decoration.
11. **Frontend forward.** Triggering "sync to PDF" with the cursor on a known
    line calls `codeToPdf` and renders a highlight overlay on the returned page.
12. **Budget.** All spec-26 tests run in well under the global 2-minute suite
    budget (target < 5s for this spec's backend unit + integration tests).

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Slow work (real LaTeX compile) is **not** run here — use fixture synctex data.

- **Unit (pytest):**
  - `parser.py`: preamble parsing (version/unit/offset), tag→file mapping, leaf
    box extraction, sp→pt + origin conversion, `forward`/`inverse` lookup
    including nearest-match fallbacks, malformed-input tolerance, and the
    `SYNCTEX_MAX_GZ_BYTES` guard. Drive with 2–3 small checked-in `.synctex.gz`
    fixtures (single-file and multi-file). Include a hand-written tiny synctex
    fixture with known coordinates so expected values are exact.
  - Coordinate round-trip property test (criterion 9) over fixture lines.
- **Integration (pytest + httpx, test DB, fake Redis):**
  - Both endpoints against a project whose output store is seeded with a fixture
    synctex.gz: success, `no_match`, `synctex_unavailable`, `422` on bad params,
    `401`/`403` auth. Use the existing output-store test seam from spec 23 to
    inject the fixture without compiling.
- **Unit (Vitest):**
  - `synctex.ts` client: param building, decoding success and the two 404
    discriminants.
  - Coordinate conversion helper (viewport px ↔ PDF points) with a mocked
    viewport.
- **E2E / component (Playwright or Vitest+RTL with mocked API):**
  - Inverse: click PDF page → editor scrolls + highlight (criterion 10).
  - Forward: sync button → PDF highlight overlay (criterion 11).
  - Keep these against a mocked synctex API and a static PDF fixture — no real
    compile in the fast tier.
- **Performance/budget note:** no compilation, no LLM, no network; parsing is in
  the low-millisecond range. The thread-offloaded parse keeps the event loop
  free under concurrent requests. Fixtures are tiny (KB).

## 9. Definition of Done

- [ ] All requirements in §5 implemented (parser, service, two endpoints,
      frontend forward + inverse wiring).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (ruff + mypy/pyright; ESLint + Prettier).
- [ ] `SYNCTEX_MAX_GZ_BYTES` and `SYNCTEX_INDEX_CACHE_SIZE` documented in
      `.env.example`; a short ADR in `docs/` records the parsing approach and the
      chosen coordinate convention.
- [ ] No Overleaf code copied (the parser is an independent implementation).
