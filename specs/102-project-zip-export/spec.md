# Spec 102 — Project ZIP Export (requirements)

## 1. Summary

This spec adds a single member-only endpoint that streams the **entire project**
as a `.zip`: every folder, every text document (at its **current** CRDT-flushed
content), and every binary file, with the tree's relative paths preserved inside
the archive. The archive is produced as a **stream** (never fully buffered in
memory) so large projects do not exhaust the worker, and entries are emitted in a
**deterministic order** so tests can assert exact contents. It is the export half
of project portability and establishes the on-disk shape a future import path
must reproduce (round-trip invariant).

## 2. Context & dependencies

- **Depends on:**
  - **11** — `Project` model + `project_service` (project name, soft-delete flag).
  - **12** — `TreeEntity` model + `inkstave.services.tree_service.get_tree`,
    `inkstave.services.tree_builder.compute_path` (flat list → relative paths).
  - **13** — `Document` model + `inkstave.services.document_service` (the
    `documents.content` column for text docs).
  - **14** — `File` model + `inkstave.services.file_service` /
    `inkstave.storage.base.ObjectStore` (`open(key) -> (stat, AsyncIterator[bytes])`).
  - **28/31** — CRDT content bridge + `inkstave.collab.flush.flush_open_project_docs`
    (materialise live rooms into `documents.content` before reading).
  - **34** — `inkstave.authorization.dependencies.require_capability` +
    `inkstave.authorization.capabilities.Capability` (member-only gate).
- **Unlocks:** the *project import* spec 101 (round-trip), project backups,
  "export to Overleaf/local" workflows.
- **Affected areas:** backend (new service + route), frontend (dashboard +
  editor menu actions), config (`.env.example`), docs (ADR for the
  streaming-vs-artifact decision).

## 3. Goals

- A `GET` endpoint under the projects API returns the whole project as `application/zip`.
- Authorization reuses the existing capability gate: **only an active member**
  may download; a non-member gets the same `404` the rest of the project API
  returns for an unauthorized/missing project.
- Text documents reflect the **latest** text: open CRDT rooms are flushed to
  `documents.content` before the export reads them (same pattern as compile).
- Binary files are streamed out of the `ObjectStore` chunk-by-chunk; the archive
  itself is streamed to the client (no full-archive buffering).
- The archive is **deterministic** (stable entry ordering, stable per-entry
  metadata) so an integration test can assert the exact set of entries.
- Empty projects, filename sanitization, and path safety are all handled.
- A documented size threshold decides sync-stream vs. async-artifact; the
  recommended default is **sync streaming** for normal projects.

## 4. Non-goals (explicitly out of scope)

- **Project import** / unzip-into-a-project. No import endpoint is created here.
  The round-trip property is documented as a desired invariant and tested only
  if an import path already exists (otherwise the test is skipped — §8).
- Selective/partial export (single folder, single file) — out of scope; the
  existing `GET …/files/{id}/content` already downloads one file.
- Compiled PDFs, history snapshots, agent state, `.git`, or any non-tree
  artifact. The export contains **only** the project file tree.
- Resumable / range downloads of the zip; the zip is a single forward stream.
- ZIP encryption, password protection, or per-entry compression tuning beyond a
  single fixed mode.

## 5. Detailed requirements

### 5.1 Data model (if any)

**None.** No new tables, columns, or migrations. The export is a pure read over
existing rows (`tree_entities`, `documents`, `files`) and blob storage.

> If the chosen async-artifact path (§5.4) is implemented for over-threshold
> projects, it stores its output through the existing `ObjectStore` under an
> `exports/{project_id}/{job_id}.zip` key with a short TTL and does **not**
> introduce a new table — the ARQ job result already tracks status. For the
> default sync-streaming implementation, no storage writes happen at all.

### 5.2 Backend / API

#### 5.2.1 New capability (authorization)

Add one capability to `inkstave.authorization.capabilities.Capability`:

```python
PROJECT_DOWNLOAD = "project_download"
```

Grant it to **every** role that already has `PROJECT_READ` (owner, editor,
viewer) in the role→capability matrix in `capabilities.py` — i.e. any active
member may export. Do **not** invent a new "downloader" role. (Reusing
`PROJECT_READ` directly is acceptable if preferred; a dedicated capability is
recommended so export can later be restricted without touching plain reads.
Pick one and be consistent — the spec's tests assert "any active member can,
non-member cannot".)

The route guards with:

```python
download_access = require_capability(Capability.PROJECT_DOWNLOAD)  # or PROJECT_READ
```

`require_capability` already returns the loaded `Project` and raises
`ProjectNotFoundError` (→ `404`) for a non-member or a missing/soft-deleted
project (see `inkstave/authorization/dependencies.py`). No new error type needed.

#### 5.2.2 Endpoint

```
GET /api/v1/projects/{project_id}/export.zip
```

- **Auth:** `Depends(download_access)` (member-only, per §5.2.1).
- **Request body:** none. No query params in the default design.
- **Response (200):** `StreamingResponse` of the zip bytes.
  - `media_type="application/zip"`.
  - Headers:
    - `Content-Disposition: attachment; filename="<safe-name>.zip"; filename*=UTF-8''<percent-encoded>`
      where `<safe-name>` is derived from the project name (see §5.2.4). Use
      `attachment` (force a download), unlike the file route's `inline`.
    - **No** `Content-Length` (the archive is streamed and its compressed size is
      not known up front). Streaming chunked transfer is expected.
- **Status / error cases:**
  - `200` — archive streams (including an empty-but-valid zip for an empty project).
  - `401` — no/invalid token (handled by `get_current_user`, upstream of the guard).
  - `404` — non-member, missing, or soft-deleted project (`ProjectNotFoundError`).
  - `413` — project exceeds `EXPORT_MAX_TOTAL_BYTES` in the sync path and the
    async-artifact path is disabled (see §5.4 / §5.5). Reuses the `AppError`
    pattern (`status_code = 413`, `error_type = "export_too_large"`).
  - A missing blob for a `file` entity (storage desynced) is **skipped with a
    logged warning**, never a hard 500 — the export of a large project must not
    fail because one orphaned blob is gone. (Mirror the best-effort posture of
    `flush_open_project_docs` and `file_service` cleanup.)

The route lives in **`inkstave/api/routes/projects.py`** (same router,
`prefix="/projects"`), next to the existing project routes, and is already
mounted via `inkstave/api/router.py`. It needs `request: Request` (to reach
`request.app.state.collab` for the flush, exactly as `compile.py` does).

Route sketch (signatures, not an implementation to copy):

```python
@router.get(
    "/{project_id}/export.zip",
    summary="Download the whole project as a .zip",
    responses=_NOT_FOUND,
)
async def export_project_zip(
    request: Request,
    project: Project = Depends(download_access),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> StreamingResponse:
    # 1. Flush live CRDT rooms so text docs export current content (spec 28/31).
    await flush_open_project_docs(
        getattr(request.app.state, "collab", None), session, project.id
    )
    # 2. Build the deterministic export plan and (optionally) enforce the size cap.
    plan = await build_export_plan(session, project.id, settings)
    # 3. Stream the archive.
    filename = zip_filename_for(project.name)
    headers = {"Content-Disposition": content_disposition(filename)}
    return StreamingResponse(
        stream_project_zip(plan, store, session, settings),
        media_type="application/zip",
        headers=headers,
    )
```

#### 5.2.3 Export service (`inkstave/services/export_service.py`, new)

A new service module owns the export logic so the route stays thin (matches the
codebase: routes are thin, logic lives in `services/`).

**Export plan (deterministic ordering).** Reuse `tree_service.get_tree` (which is
already bounded by `tree_max_nodes`) + `tree_builder.compute_path` to turn the
flat entity list into `(relative_path, entity)` pairs:

```python
@dataclass(frozen=True)
class ExportEntry:
    path: str                 # POSIX relative path inside the zip, e.g. "chapters/intro.tex"
    type: TreeEntityType      # folder | doc | file
    entity_id: UUID
    storage_key: str | None   # set for file entities
    size_bytes: int           # doc UTF-8 size or file size; 0 for folders


async def build_export_plan(
    session: AsyncSession, project_id: UUID, settings: Settings
) -> list[ExportEntry]:
    ...
```

Rules for `build_export_plan`:

- Skip the root entity (`is_root`); its derived path is `""`. Children's paths
  come from `compute_path(entity, by_id)` and are already root-relative.
- **Folders:** emit an explicit directory entry `path + "/"` so empty folders
  survive the round-trip. (A folder with children does not strictly need an
  explicit entry, but emitting one for every folder keeps the archive's structure
  explicit and the ordering simple.)
- **Docs:** the content is read from `documents.content` (post-flush). Use a
  bulk read of `Document.entity_id, Document.content` for the project's doc
  entities (a single `SELECT … WHERE project_id = :pid`) rather than N queries.
  Empty docs export as a zero-byte file at their path.
- **Files:** carry `storage_key` and `size_bytes` from the `files` row (one bulk
  `SELECT` keyed by `project_id`). Bytes are streamed at archive time, **not**
  loaded here.
- **Deterministic order:** sort entries by their full `path` using a stable key.
  Recommended: sort by the tuple of path segments, case-sensitively, ascending,
  with a parent folder's directory entry emitted **before** its children. A
  simple, test-assertable rule: sort by `path` (the directory entry `"a/"`
  naturally precedes `"a/b.tex"` under plain string ordering because `/` (0x2F)
  < alphanumerics is **not** guaranteed — instead sort by the *segment list*
  `path.split("/")` so a folder always sorts before its contents). Document the
  exact comparator in a code comment; the integration test asserts the resulting
  order.
- **Size cap (sync path):** sum doc `size_bytes` + file `size_bytes`. If the sum
  exceeds `settings.export_max_total_bytes` and the async path is disabled, raise
  `ExportTooLargeError` (413) *before* any bytes are streamed.

**Streaming zip builder.** A pure-streaming generator that yields archive bytes:

```python
async def stream_project_zip(
    plan: list[ExportEntry],
    store: ObjectStore,
    session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[bytes]:
    ...
```

Implementation requirements:

- Use Python's stdlib **`zipfile.ZipFile`** writing into a small custom
  *streaming buffer* object (a `io.RawIOBase`/object exposing `write()` and
  `flush()` that accumulates into a `bytearray`, which the generator drains and
  yields after each entry / each chunk, then clears). This gives a true stream
  without a third-party dependency and without holding the whole archive. Do not
  call `ZipFile(in_memory_bytesio)` and yield at the end — that buffers
  everything and violates the streaming requirement.
  - Per-entry: open with `zf.open(zinfo, mode="w")` and write the doc bytes or
    pump the file's `AsyncIterator[bytes]` chunk-by-chunk, draining the buffer to
    the consumer between chunks so memory stays O(chunk + one entry header).
  - For file entities: `stat, stream = await store.open(entry.storage_key)`; on
    `ObjectNotFoundError`, log a warning and **skip** the entry (do not abort).
- **Determinism of bytes:** set a **fixed** `ZipInfo.date_time` (e.g.
  `(1980, 1, 1, 0, 0, 0)`, the zip epoch) and a fixed `external_attr`/compression
  mode for every entry, so the archive is byte-reproducible given the same tree.
  Use `ZIP_DEFLATED` for docs (text compresses well) — but note DEFLATE output is
  only byte-identical with the same zlib; the integration test asserts **entry
  names + per-entry uncompressed content**, not raw archive bytes. (A unit test
  may additionally assert ordering of `namelist()`.)
- Chunk size for pumping file bytes: `settings.storage_stream_chunk_bytes`
  (already defined, default 65536).
- The generator must `await` between chunks (it already does, pulling from an
  async store stream) so the event loop is not starved on a large project.

#### 5.2.4 Filename sanitization & path safety

- **Archive filename** (`zip_filename_for(project_name)`):
  - Strip directory separators and control chars; collapse whitespace; trim.
  - Disallow `"`, `\r`, `\n` in the header value (reuse the spirit of
    `files.py::_sanitize_header_filename`).
  - Fall back to `"project"` when the sanitized name is empty.
  - Append `.zip`. Provide a `Content-Disposition` with both a plain ASCII
    `filename="…"` (non-ASCII stripped/replaced) **and** RFC 5987
    `filename*=UTF-8''<percent-encoded>` for Unicode names.
- **Entry paths** inside the archive: paths come from `compute_path`, which is
  built from `validate_name_segment`-checked names (spec 12 already forbids `/`,
  `..`, control chars and reserved names in entity names). The builder must
  still assert each segment is non-empty and contains no `/` or `\\` and is not
  `.`/`..` as a defensive guard (zip-slip protection), raising/skipping if
  violated. Always use forward slashes in archive paths.

### 5.3 Frontend / UI

Add a **"Download as .zip"** action in two places, both using existing shadcn
components already present in the repo (`DropdownMenu*`, `Button`, `lucide-react`
icons such as `Download`).

#### 5.3.1 API helper

Extend `src/features/projects/api.ts` with a download helper that uses the
existing binary path of the API client. The client already exposes
`apiClient.getBytes(path)` (`src/lib/api-client.ts`) which performs the authed,
refresh-aware request and returns an `ArrayBuffer`:

```ts
export async function downloadProjectZip(id: string, name: string): Promise<void> {
  const buf = await apiClient.getBytes(`/api/v1/projects/${id}/export.zip`);
  const blob = new Blob([buf], { type: "application/zip" });
  triggerBrowserDownload(blob, `${sanitizeName(name) || "project"}.zip`);
}
```

`triggerBrowserDownload` creates an object URL, a temporary `<a download>`,
clicks it, then revokes the URL (a small util in `src/lib/`). Using `getBytes`
keeps auth handling (Bearer token + 401-refresh) consistent with the rest of the
app; a plain `<a href>` would not carry the JWT.

#### 5.3.2 Dashboard menu

In `src/features/projects/project-table.tsx` (`RowActionsMenu`), add a
`DropdownMenuItem` "Download as .zip" with a `Download` icon, between "Open" and
"Rename". Wire a new `onDownload(project)` action through `RowActions` and the
`ProjectTable` → `projects-page.tsx` chain (mirror how `onRename`/`onDelete` are
threaded). The handler:

- sets a per-row loading state (disable the item / show a spinner) while the zip
  is being fetched,
- on success the browser download begins,
- on error shows the app's existing toast/error surface with a retry-friendly
  message,
- i18n: add keys (e.g. `actionsMenu.download`, `download.error`) to
  `src/i18n/locales/en` and `…/pt` matching existing menu keys.

#### 5.3.3 In-editor menu

Add the same action to the editor's project/file menu (the editor workspace,
`src/features/editor/…` — wherever the project-level menu lives; if none exists
yet, add it to the editor header/toolbar as a shadcn `Button` with the `Download`
icon). Same loading/error semantics. Reuse the `downloadProjectZip` helper.

#### 5.3.4 States & a11y

- **Loading:** the trigger shows a spinner / disabled state; concurrent clicks
  are ignored while a download is in flight.
- **Error:** toast with the server message; the menu remains usable for retry.
- **Empty project:** still downloads (a valid, near-empty zip) — no special UI.
- **a11y:** the action has an accessible label; the menu item is keyboard
  reachable; the spinner has `aria-live`/`aria-busy` as the codebase already does
  for async actions.

### 5.4 Real-time / jobs / external integrations

- **CRDT flush (required):** before reading doc content, call
  `inkstave.collab.flush.flush_open_project_docs(request.app.state.collab,
  session, project.id)` so currently-open rooms are materialised into
  `documents.content` (best-effort; rooms on another instance are skipped). This
  is the identical pattern used by `compile.py` (enqueue) and keeps exported text
  current.
- **Sync streaming vs. async artifact (decision):**
  - **Default / recommended:** **synchronous streaming** via `StreamingResponse`
    for all normal projects. It is simplest, needs no new storage or job, and the
    per-entry streaming keeps memory bounded regardless of project size in
    practice.
  - **Threshold:** define `EXPORT_MAX_TOTAL_BYTES` (sum of doc + file bytes). If a
    project exceeds it:
    - With async export **disabled** (default): return `413 export_too_large`.
    - With async export **enabled** (`EXPORT_ASYNC_ENABLED=true`, optional,
      may be deferred): enqueue an **ARQ job** `build_project_export(project_id,
      user_id)` that produces the zip into the `ObjectStore` under
      `exports/{project_id}/{job_id}.zip` (streaming the same builder to the
      store), and the endpoint returns `202` + a poll/download URL. **The async
      path is optional for this spec**; implementing only the sync path + the
      `413` cap satisfies the requirements. If implemented, the heavy work must
      be in the ARQ worker (per `CLAUDE.md`) and mocked/skipped in the fast test
      tier.
  - Keep the threshold generous (default 200 MiB) so it never trips in normal use
    or in tests; tests that exercise the cap set a tiny override.
- No LLM, Tectonic, or new WebSocket messages are involved.

### 5.5 Configuration

New env vars (add to `.env.example`, in a new `# --- Project export (spec 102) ---`
section near the storage block), and corresponding fields on the appropriate
config mixin in `inkstave/config_groups.py` (Storage or a new Export group;
follow the existing `Field`/default + snake_case pattern, e.g.
`max_upload_bytes`):

| Env var | Setting field | Type | Default | Meaning |
|---|---|---|---|---|
| `EXPORT_MAX_TOTAL_BYTES` | `export_max_total_bytes` | int | `209715200` (200 MiB) | Max total (doc + file) bytes for the **sync** stream path; over this → 413 (or async if enabled). |
| `EXPORT_STREAM_CHUNK_BYTES` | `export_stream_chunk_bytes` | int | reuse `storage_stream_chunk_bytes` (65536) if you prefer one knob | Chunk size used to pump file bytes into the archive and drain the stream buffer. |
| `EXPORT_ASYNC_ENABLED` | `export_async_enabled` | bool | `false` | When true, over-threshold projects build via an ARQ job + artifact instead of returning 413. Optional in this spec. |

> If you reuse `storage_stream_chunk_bytes` instead of adding
> `EXPORT_STREAM_CHUNK_BYTES`, drop that row and say so in the ADR; do not add an
> unused setting.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently. **Verified present** in the cloned repo:

- `services/web/app/src/Features/Downloads/ProjectZipStreamManager.mjs` — how
  Overleaf assembles a project into a **streaming** zip (archiver-based): it pipes
  each doc's text and each file's blob stream into a zip stream rather than
  buffering. Learn the *streaming* shape (one entry at a time, paths preserved);
  Inkstave uses stdlib `zipfile` + an async generator instead of Node's
  `archiver`/streams.
- `services/web/app/src/Features/Downloads/ProjectDownloadsController.mjs` — how
  the controller sets `Content-Type: application/zip` and a sanitized
  `Content-Disposition` filename derived from the project name, and wires the zip
  stream to the HTTP response. Learn the header shape; write our own.

No other Overleaf path is needed. There is **no** Overleaf equivalent for the
CRDT-flush step — that is Inkstave-specific (spec 28/31).

## 7. Acceptance criteria

1. **Endpoint exists & is member-gated.** Given an active member of a project,
   When they `GET /api/v1/projects/{id}/export.zip`, Then they receive `200` with
   `Content-Type: application/zip` and a `Content-Disposition: attachment;
   filename="…zip"` header.
2. **Non-member denied.** Given a user who is not a member (and the project is not
   theirs), When they call the endpoint, Then they receive `404` (same as other
   project routes) and **no** archive bytes.
3. **Complete tree.** Given a project with nested folders, multiple `.tex` docs,
   and at least one binary file, When exported, Then the zip contains exactly one
   entry per non-root entity at its correct relative path (folders as directory
   entries, docs and files at their paths), and nothing extra.
4. **Current text content.** Given a doc whose live CRDT room has unsaved-to-column
   edits, When the project is exported, Then the doc entry's bytes equal the
   **flushed** current text (the flush ran before the read), not stale column text.
   (Tested by stubbing the flush/manager to mutate `documents.content`.)
5. **Binary fidelity.** Given an uploaded binary file, When exported, Then its zip
   entry's uncompressed bytes are byte-identical to the stored blob.
6. **Deterministic ordering.** Given the same tree, When exported twice, Then
   `namelist()` is identical and in the documented order; the integration test
   asserts the exact expected ordered list of entry names.
7. **Empty project.** Given a project with only a root folder (no children), When
   exported, Then the response is `200` and a **valid** (openable) zip with zero
   file entries.
8. **Streaming / memory.** The archive is produced by an async generator feeding
   `StreamingResponse`; no code path constructs the full archive in a single
   in-memory buffer before responding. (Verified by inspection + a test that the
   builder yields multiple chunks for a multi-file project.)
9. **Filename sanitization & path safety.** Given a project named e.g.
   `My "Thesis"/v2\n`, When exported, Then the `Content-Disposition` filename is
   sanitized (no `"`, `/`, CR/LF; non-empty; ends `.zip`) and no archive entry
   path escapes the archive root (no `..`, no absolute paths).
10. **Size cap.** Given `EXPORT_MAX_TOTAL_BYTES` set below the project's total and
    async disabled, When exported, Then the endpoint returns `413
    export_too_large` before streaming any bytes.
11. **Missing blob tolerated.** Given a `file` entity whose blob is absent from
    the store, When exported, Then the export still succeeds (that entry skipped,
    a warning logged), not a 500.
12. **Frontend action.** Given the dashboard project list, When the user opens a
    project's actions menu, Then a "Download as .zip" item is present; clicking it
    fetches the zip (authed) and triggers a browser download, showing a loading
    state and surfacing errors via the app's error UI. The same action exists in
    the editor.
13. **Round-trip (conditional).** *If* a project-import path exists, Then a project
    exported and re-imported reproduces the same tree (same paths, doc contents,
    file bytes). If no import path exists, this is recorded as a desired invariant
    and the test is `skip`ped with a reason.

## 8. Test plan

> All tests combined must keep the suite under 2 minutes. No large archives in
> the fast tier; the async-artifact path (if built) is mocked.

- **Unit (pytest) — `export_service`:**
  - `build_export_plan` over a small in-memory/DB tree (root → folder `chapters`
    → doc `intro.tex`, root doc `main.tex`, root file `logo.png`) returns the
    expected ordered `ExportEntry` list with correct `path`, `type`, sizes, and
    deterministic ordering (folders before their children; stable comparator).
  - `stream_project_zip` for that plan, collected into a `BytesIO` and re-opened
    with `zipfile.ZipFile`, yields the expected `namelist()` (exact order) and the
    expected per-entry uncompressed content (`main.tex` text, `intro.tex` text,
    `chapters/` dir entry, `logo.png` bytes). Uses a fake `ObjectStore` returning
    a known byte stream.
  - Determinism: building the zip twice yields identical `namelist()` and
    identical per-entry contents; fixed `date_time` is applied (assert a
    `ZipInfo.date_time` is the fixed epoch).
  - Filename helper: `zip_filename_for` sanitizes quotes/slashes/CRLF and falls
    back to `"project"`; `content_disposition` includes both `filename=` and
    `filename*=`.
  - Streaming: asserts the generator yields **more than one** chunk for a
    multi-entry plan (proxy for "not one big buffer").
- **Unit (Vitest) — frontend:**
  - `downloadProjectZip` calls `apiClient.getBytes` with the right path and
    triggers `triggerBrowserDownload` with a `application/zip` blob and the
    sanitized filename (mock the client + URL/anchor).
  - `RowActionsMenu` renders the "Download as .zip" item and calls `onDownload`;
    loading disables it; an error path surfaces the toast.
- **Integration (pytest + httpx + test DB + fake/real ObjectStore):**
  - Seed a project (member = caller) with the small tree above; hit
    `GET …/export.zip`; read the body fully in-memory; open with `zipfile`;
    assert status `200`, headers (`application/zip`, `attachment` + filename),
    exact ordered `namelist()`, and per-entry content/bytes (AC 3,5,6).
  - **Authorization:** a second user who is *not* a member gets `404` and an empty
    body (AC 2). Owner and an invited editor/viewer both succeed (AC 1).
  - **Current content:** monkeypatch/stub the collab flush so it writes new text
    into `documents.content`; assert the exported doc reflects it (AC 4).
  - **Empty project:** root-only project exports a valid zero-entry zip (AC 7).
  - **Size cap:** override `export_max_total_bytes` to a tiny value; assert `413
    export_too_large` and that no zip body is produced (AC 10).
  - **Missing blob:** delete the blob for a file entity in the store, keep the row;
    assert the export still returns `200` and omits that entry (AC 11).
- **E2E (Playwright):** on the dashboard, open a seeded project's actions menu,
  click "Download as .zip", and assert a download event occurs and the received
  file is a non-empty `application/zip` (use Playwright's `waitForEvent("download")`
  / `download.path()`), with a small seeded project so it's fast.
- **Round-trip (conditional):** add a test that exports then imports and compares
  trees **only if** an import API exists; otherwise `pytest.mark.skip(reason=
  "project import not implemented yet (no import spec)")`.
- **Performance/budget note:** all fixtures use tiny trees (a few KB total); no
  real Tectonic/LLM; the async-artifact ARQ job (if implemented) is exercised only
  via a mocked enqueuer, never run for real in the fast tier. Streaming is
  validated with small inputs.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (endpoint, `export_service`, capability,
      streaming builder, filename/path safety, CRDT flush, config).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (round-trip test skipped-with-reason if no
      import path exists).
- [ ] The archive is streamed (no full-archive in-memory buffer) and entries are
      deterministically ordered.
- [ ] Member-only authorization enforced; non-member gets `404`.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`;
      ESLint + Prettier + strict TS on the frontend).
- [ ] New env vars documented in `.env.example` and mirrored on the config mixin;
      any reused-instead-of-added knob noted in the ADR. ADR added under `docs/`
      for the sync-stream-vs-artifact decision.
- [ ] **No Overleaf code copied** — the streaming-zip and header approaches are
      independently implemented with stdlib `zipfile`.
