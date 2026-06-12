# Spec 101 — Project Import from .zip (requirements)

## 1. Summary

This spec lets a user **import a project as a `.zip`** exported from another
LaTeX platform (Overleaf, ShareLaTeX, a local `latexmk` tree, etc.). The upload
endpoint **always creates a brand-new Inkstave project** and hands the archive to
an ARQ background job that unpacks it and reconstructs the file tree: folders,
text documents (→ document-content, spec 13), and binary files (→ binary storage,
spec 14), reusing the existing `tree_service` / `document_service` /
`file_service` / `ObjectStore` modules. The main `.tex` file is detected and set
as the project's `root_doc_id`. Unpacking is bounded and security-hardened
against **zip-slip / path traversal** and **zip-bombs**, and is mocked/bounded in
tests so the suite stays under two minutes.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 11** — `Project` model (`projects.root_doc_id`,
    `services/project.py::create_project`) and the projects API router
    (`api/routes/projects.py`).
  - **Spec 12** — `TreeEntity` / `TreeEntityType` model, `tree_service`
    (`create_entity`, `ensure_root`, `get_tree`) and `tree_builder`, plus
    `services/safe_path.py::validate_name_segment` (the SafePath rules).
  - **Spec 13** — `document_service` (`ensure_document`, `set_content_from_collab`
    or a new bulk seed) and the `Document` model.
  - **Spec 14** — `file_service` (`upload_file`, `_storage_key`) and the
    `ObjectStore` abstraction (`storage/base.py`).
  - **Spec 16** — projects dashboard (`frontend/src/features/projects/`).
  - **Spec 22** — async ARQ jobs: the **status/poll/SSE pattern** to mirror
    (`compile/coordinator.py`, `compile/enqueuer.py`, `compile/jobs.py`,
    `api/routes/compile.py`, `compile/worker.py`, the `Compile` status model).
  - **Spec 52** — upload hardening helpers (`security/uploads.py`:
    `sanitize_filename`, `extension_allowed`, `content_matches_extension`,
    `sniff_content_type`).
- **Unlocks:** future "duplicate/clone project", "import from Git", and template
  galleries can reuse the tree-reconstruction service built here.
- **Affected areas:** backend (new model + migration, new service module, new ARQ
  job, new routes, new config), frontend (dashboard import action), docs (one ADR),
  `.env.example`.

## 3. Goals

- A multipart upload endpoint under the projects API accepts a single `.zip` and
  **always** creates a NEW project; it returns the new project id immediately
  (the heavy unpack runs asynchronously).
- An ARQ job (`import_project_zip`) unpacks the archive and reconstructs the tree
  by reusing the existing tree / document / file services — never duplicating
  their logic.
- The main `.tex` is detected (`\documentclass` heuristic, then a `main.tex`
  fallback) and set as `projects.root_doc_id`.
- Robust, explicitly-tested security: **zip-slip** (traversal/absolute paths
  rejected), **never extract symlinks**, and **zip-bomb** bounds (total
  uncompressed size, per-file size, entry count) enforced from env vars.
- UTF-8-with-fallback decoding for text files; deterministic binary-vs-text
  classification.
- A status surface (poll + SSE) consistent with spec 22 so the frontend can wait
  for the import to finish, then open the new project.
- The whole feature is exercised by fast tests (tiny in-memory zips); no real
  heavy unzip in the fast tier; suite stays < 2 minutes.

## 4. Non-goals (explicitly out of scope)

- Merging an archive into an **existing** project (import is create-only).
- Importing `.tar`, `.tar.gz`, `.7z`, `.rar`, or bare directories.
- Re-export / download-as-zip (a separate later spec).
- Converting `.doc`/`.docx`/`.md` to LaTeX (Overleaf's
  `DocumentConversionManager` behaviour) — out of scope; such files are stored
  as-is if their extension is allowed, otherwise skipped.
- Streaming per-entry progress to the UI. The UI shows upload progress + a single
  "importing…" state, then "done/failed" (coarse status, not per-file).
- Collaboration/realtime seeding (the CRDT room materialises lazily on first open
  via the existing spec-28 seam).

## 5. Detailed requirements

### 5.1 Data model

A new table tracks one import job's lifecycle, mirroring the `compiles` table
shape (spec 22) so the status surface is consistent.

**Table `project_imports`** (`db/models/project_import.py`,
`UUIDPrimaryKeyMixin` + `TimestampMixin`):

| Column          | Type                         | Notes |
|-----------------|------------------------------|-------|
| `id`            | UUID PK                      | import id (returned to the client). |
| `project_id`    | UUID FK→`projects.id` (CASCADE), not null | the new project created up-front. |
| `requested_by`  | UUID FK→`users.id` (CASCADE), not null | the uploader. |
| `status`        | `String(16)`, not null, default `queued` | see `ProjectImportStatus`. |
| `source_key`    | `String(512)`, not null      | `ObjectStore` key of the staged upload blob. |
| `original_filename` | `String(255)`, nullable  | the client filename (sanitized). |
| `source_bytes`  | `BigInteger`, not null, default 0 | compressed upload size. |
| `job_id`        | `Text`, nullable             | ARQ job id. |
| `entries_total` | `Integer`, nullable          | entries the job decided to import. |
| `entries_imported` | `Integer`, nullable       | entries actually reconstructed. |
| `error_type`    | `String(64)`, nullable       | machine code, e.g. `zip_slip`, `zip_too_large`. |
| `error_message` | `Text`, nullable             | human message (truncated to 1000). |
| `started_at`    | `DateTime(tz)`, nullable      | |
| `finished_at`   | `DateTime(tz)`, nullable      | |

Enum `ProjectImportStatus(StrEnum)`: `queued`, `running`, `success`,
`partial` (imported, but some entries skipped), `failure`, `error`.
Helpers `is_terminal()` / `is_active()` analogous to
`db/models/compile.py`.

Constraints/indexes:
- `Index("ix_project_imports_project_id", "project_id")`.
- `Index("ix_project_imports_requester", "requested_by", text("created_at DESC"))`.
- `CheckConstraint("source_bytes >= 0", ...)`.

**Migration:** one new Alembic migration adding `project_imports` (and its enum
handled as a `String(16)`, matching how `compiles.status` is stored). Never edit a
released migration. The created project itself uses the existing `projects` /
`tree_entities` tables — no schema change there.

`projects.root_doc_id` already exists (spec 11) and is set by the job.

### 5.2 Backend / API

#### 5.2.1 Upload endpoint — `POST /api/v1/projects/import`

- **Router:** add to the existing `projects` router (`api/routes/projects.py`)
  or a sibling `api/routes/project_import.py` included from `api/router.py`.
- **Auth:** `Depends(get_current_user)` — any authenticated user (this creates a
  project they will own; there is no pre-existing project to authorize against).
- **Rate limit:** `Depends(rate_limit_named("upload"))` (reuse the spec-52 named
  limiter used by `files.upload_file`).
- **Request:** `multipart/form-data`
  - `file: UploadFile` (required) — the `.zip`.
  - `name: str | None = Form(None)` (optional) — desired project name; if omitted,
    derive from the archive (see §5.4.4), else fall back to the zip filename stem,
    else `"Imported project"`.
- **Synchronous validation (before enqueue, cheap, no full read):**
  1. Extension must be `.zip` (via `extension_of`) and declared/ sniffed type
     consistent (`application/zip`, `application/x-zip-compressed`, or
     `application/octet-stream` with a `PK\x03\x04` magic-byte head). Otherwise
     `415 unsupported_media_type`.
  2. Stream the body to a staged `ObjectStore` blob under
     `imports/{import_id}/source.zip`, enforcing `import_max_zip_bytes` while
     streaming (same chunked guard as `file_service.upload_file`); exceeding it →
     `413 file_too_large`, and the partial blob is best-effort-deleted.
- **Side effects, in one DB transaction:**
  1. `create_project(session, user.id, effective_name)` (spec 11) — the NEW
     project (root folder + owner membership created by that service).
  2. Insert a `project_imports` row (`status=queued`, `source_key`,
     `source_bytes`, `original_filename`).
  3. Enqueue `import_project_zip(import_id)` via a new `ImportEnqueuer`
     (§5.4.1); persist the returned `job_id`.
- **Response:** `202 Accepted`, body `ProjectImportRead` (Pydantic, §5.2.4)
  including `project_id` (the NEW project) and `import_id` and `status`.
- **Error envelope:** the standard `ErrorEnvelope`; documented `responses` for
  `413` and `415`.
- **Important:** the project is created **immediately** so the id can be returned
  and the dashboard can show a placeholder; if the async unpack later fails, the
  project remains but its import row is `failure`/`error` (the UI surfaces this;
  the user may delete the empty project via the existing spec-11 delete). This is
  the simplest behaviour consistent with returning a project id up-front. (An
  alternative — soft-delete the project on hard failure — is allowed if the
  implementer prefers; document the choice in the ADR.)

#### 5.2.2 Status endpoints (mirror spec 22)

- `GET /api/v1/projects/{project_id}/import` → latest `ProjectImportRead` for the
  project (404 `import_not_found` if none). Auth: `require_capability(PROJECT_READ)`.
- `GET /api/v1/projects/{project_id}/import/{import_id}` → that import's status.
- `GET /api/v1/projects/{project_id}/import/{import_id}/events` → SSE stream of
  status transitions, reusing the spec-22 SSE plumbing
  (`compile/stream.py::sse_stream` / `publish_status`, generalised, or a small
  parallel `import/stream.py`). The job publishes a status payload on every
  transition exactly as `run_compile` does via `publish_status`.

#### 5.2.3 Tree-reconstruction service (`services/zip_import.py`)

Pure-ish reconstruction logic, isolated so it can be unit-tested with in-memory
zips and so the ARQ job stays thin (mirrors how `compile/jobs.py` delegates to
`CompileService`).

Key signatures:

```python
@dataclass(frozen=True)
class ImportLimits:
    max_zip_bytes: int
    max_uncompressed_bytes: int
    max_file_bytes: int
    max_entries: int
    allowed_extensions: frozenset[str]      # lower-cased, incl. dot

@dataclass(frozen=True)
class PlannedEntry:
    parts: tuple[str, ...]                  # validated, traversal-free segments
    is_dir: bool
    uncompressed_size: int                  # from the zip central directory
    classification: Literal["text", "binary"]

class ZipImportError(AppError):             # 422 family, error_type per subclass
    ...
class ZipSlipError(ZipImportError):    error_type = "zip_slip"
class ZipBombError(ZipImportError):    error_type = "zip_too_large"
class ZipEntryCountError(ZipImportError): error_type = "zip_too_many_entries"
class InvalidZipError(ZipImportError): error_type = "invalid_zip"
class SymlinkEntryError(ZipImportError): error_type = "zip_symlink"

def plan_entries(zf: zipfile.ZipFile, limits: ImportLimits) -> list[PlannedEntry]:
    """Validate the central directory WITHOUT extracting bytes.

    - Reject the archive (InvalidZipError) if zipfile.testzip-style open fails.
    - For each entry:
        * Normalise: replace '\\' with '/', split on '/'.
        * Reject absolute paths (leading '/') and any '..' / '.' segment
          (ZipSlipError); validate each segment with validate_name_segment
          (spec 12) — control chars / reserved names / separators rejected.
        * Reject symlinks: (external_attr >> 16) & S_IFLNK == S_IFLNK
          (SymlinkEntryError). Never read or follow them.
        * Skip ignorable junk: '__MACOSX/...', '.DS_Store', entries whose
          first segment is '.git' (returned as ignored, not imported).
        * Classify text vs binary by extension (§5.4.3); a disallowed extension
          is skipped (counted as 'skipped'), not fatal — unless skipping leaves
          zero importable entries (then InvalidZipError 'empty_archive').
    - Enforce cumulative caps as it walks:
        * count of kept entries  > max_entries        -> ZipEntryCountError
        * any entry.file_size    > max_file_bytes      -> ZipBombError
        * sum(file_size)         > max_uncompressed_bytes -> ZipBombError
      All caps use the *declared* uncompressed sizes from the central directory,
      so a bomb is rejected BEFORE any decompression. The job additionally caps
      bytes actually decompressed per entry (defence in depth, §5.4.2).
    """

async def reconstruct_tree(
    session, store, project_id, zf, planned, *, settings,
) -> ImportOutcome:
    """Create folders/docs/files for the planned entries, reusing services.

    - Folders: ensure each intermediate path segment exists as a folder via
      tree_service.create_entity(folder) (idempotent per (parent, name) lower);
      cache created folder ids by path to avoid re-querying.
    - Text entries: create a doc entity (tree_service.create_entity(doc)),
      decode bytes (§5.4.3), then seed content via the spec-13 service
      (e.g. document_service.set_content_from_collab / a new seed_document
      helper) — NOT replace_content (no base_version to honour on a fresh doc).
      Enforce settings.max_document_bytes; oversize text is skipped + recorded.
    - Binary entries: create a file entity + blob exactly like
      file_service.upload_file, but reading from the per-entry zip stream
      (store.put with an async generator); reuse sniff_content_type + the
      spec-52 extension/MIME consistency checks.
    - Per-entry decompression is bounded: stop and raise ZipBombError if the
      decompressed bytes exceed the declared size by a tolerance, or exceed
      max_file_bytes.
    - Returns counts (created folders/docs/files, skipped) and the chosen
      root doc path (or None).
    """

def detect_root_doc(planned: list[PlannedEntry], text_blobs: dict[tuple[str,...], bytes]) -> tuple[str,...] | None:
    """Pick the main .tex: first a .tex whose decoded text contains
    '\\documentclass' (shallowest path wins, ties broken by 'main.tex' name then
    lexicographically); else a top-level 'main.tex'; else the only .tex; else None.
    """
```

`ImportOutcome` carries `root_doc_entity_id: UUID | None`; the job writes it to
`projects.root_doc_id` (reusing a small `project_service` setter, or a direct
`UPDATE` in the same session).

#### 5.2.4 Pydantic schemas (`schemas/project_import.py`)

```python
class ProjectImportRead(BaseModel):
    import_id: UUID            # = row.id
    project_id: UUID
    status: ProjectImportStatus
    entries_total: int | None
    entries_imported: int | None
    error_type: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
```

A small validator aliases `row.id` → `import_id` (or a computed field), matching
how `CompileStatusResponse` is built from a `Compile` row.

#### 5.2.5 Repository (`services/import_repository.py` or inline)

A thin `ProjectImportRepository` mirroring `CompileRepository`: `create(...)`,
`get(project_id, import_id)`, `get_latest(project_id)`, `update(row, **fields)`.

### 5.3 Frontend / UI

On the projects dashboard (`frontend/src/features/projects/`):

- **Header action.** Add an **"Import project (.zip)"** button next to the
  existing "New project" button in `ProjectsHeader` (`projects-page.tsx`),
  using the shadcn `Button` (`variant="outline"`, `Upload` lucide icon). Opens an
  `ImportProjectDialog`.
- **`ImportProjectDialog`** (new `import-project-dialog.tsx`, shadcn `Dialog`):
  - A file input restricted to `.zip` (`accept=".zip"`), or a simple drop zone.
  - Optional project-name `Input` (placeholder = derived/zip stem).
  - On submit: `POST /api/v1/projects/import` as `FormData` via a new
    `api.importProjectZip(file, name?)` (add to `features/projects/api.ts`),
    using an upload that reports **progress** (XHR/`onUploadProgress`) — show a
    shadcn `Progress` bar during upload. The existing `apiClient` is JSON-only;
    add an `apiClient.upload`/raw-`fetch`+`XMLHttpRequest` helper for multipart
    with progress (keep auth header handling identical to `apiClient`).
  - After `202`, switch to an **"Importing…"** state and **poll**
    `GET /projects/{project_id}/import/{import_id}` (react-query, `refetchInterval`
    while non-terminal) or subscribe to the SSE `…/events` endpoint (mirror how
    the compile UI consumes spec-22 events, if that pattern exists; otherwise
    poll — simplest).
  - **Success / partial** → toast, invalidate `PROJECTS_KEY`, close the dialog,
    and `navigate('/projects/{project_id}')` (open the new project).
  - **Failure / error** → inline error in the dialog (map `error_type` to a
    friendly i18n string: zip-slip, too-large, too-many-entries, invalid-zip,
    empty), keep the dialog open so the user can retry; offer a "Delete the empty
    project" affordance (calls existing `deleteProject`).
- **State machine** in a `use-import-project.ts` hook:
  `idle → uploading(progress%) → processing → done | failed`. Disable the submit
  button while not `idle`; cancel polling on unmount.
- **i18n:** new keys under the `projects` namespace
  (`import.title`, `import.cta`, `import.uploading`, `import.processing`,
  `import.success`, `import.errors.*`). English only.
- **Accessibility:** the dialog has a labelled file input, the progress bar has
  `aria-label`/`aria-valuenow`, errors are announced via the existing toast/inline
  pattern used by the other project dialogs.
- **Empty/loading/error states** reuse the existing dialog conventions in
  `project-dialogs.tsx`.

### 5.4 Real-time / jobs / external integrations

#### 5.4.1 Enqueuer (`services/import_enqueuer.py`)

`ImportEnqueuer`, identical in shape to `compile/enqueuer.py::ArqEnqueuer` and
`agent/api/enqueuer.py`:

```python
class ImportEnqueuer:
    def __init__(self, pool: ArqRedis, queue_name: str) -> None: ...
    async def enqueue(self, import_id: UUID) -> str | None:
        job = await self._pool.enqueue_job(
            "import_project_zip", str(import_id),
            request_id=request_id_var.get(), _queue_name=self._queue_name,
        )
        return job.job_id if job is not None else None
```

Reuse the single shared queue (`settings.compile_queue_name`, one worker) as the
other enqueuers do. Add a `get_import_enqueuer` dependency in `dependencies.py`
following the existing `get_compile_enqueuer` pattern (lazy shared `arq_pool` on
`app.state`). Tests override it with a fake that runs the job inline.

#### 5.4.2 The job (`services/import_jobs.py::import_project_zip`)

Signature and lifecycle mirror `compile/jobs.py::run_compile`:

```python
async def import_project_zip(
    ctx: dict[str, Any], import_id: str, *, request_id: str | None = None
) -> dict[str, Any]:
```

Body:
1. Bind observability context (`bind_context`/`clear_context`), `track_job`.
2. Open a DB session via `ctx["session_factory"]`; load the import row; if missing
   or already terminal → return early.
3. Re-authorize defence-in-depth: confirm `row.requested_by` still owns
   `row.project_id` (reuse `project_service.get_owned_project` or `role_for`);
   if not, mark `error` and return (mirrors the spec-34 re-check in `run_compile`).
4. Mark `running`, `started_at`; `publish_status`.
5. Stream the staged blob from `ObjectStore` (`store.open(row.source_key)`) into a
   **temp file** under a bounded scratch dir (`import_workdir_root`), enforcing
   `max_zip_bytes` again as it copies. Open it with the stdlib `zipfile` (random
   access requires a seekable file — hence the temp copy; that copy is bounded
   and cleaned up in a `finally`, like the compile workdir backstop).
6. `planned = plan_entries(zf, limits)` (all security checks — §5.2.3).
7. `outcome = await reconstruct_tree(...)`; set `projects.root_doc_id` from
   `outcome.root_doc_entity_id`.
8. Commit; set terminal status: `success` (all kept entries imported), `partial`
   (some skipped), or — on a `ZipImportError` — `failure` with `error_type` /
   `error_message`; any unexpected exception → `error` (job never crashes).
9. `publish_status` on every transition; **always** delete the staged source blob
   and the temp file in a `finally` (the import is a one-shot; the upload is not
   retained).
10. Return a small summary dict (like `_summary` in `compile/jobs.py`).

The job is registered in `compile/worker.py`'s `WorkerSettings.functions`
alongside `run_compile` / `run_agent_turn` (single worker), with its startup ctx
already providing `settings`, `session_factory`, `redis`, and `object_store`.

**Test seam:** `reconstruct_tree` / `plan_entries` are pure functions over an
in-memory `zipfile.ZipFile`; tests call them directly and call the job with a
hand-built `ctx` + a fake enqueuer that runs inline — **never** the real ARQ
worker, **never** a large archive. This keeps the heavy-path out of the fast tier.

#### 5.4.3 Encoding & binary/text classification

- **Classification is by extension first** (deterministic, no content sniff for
  the decision): a configurable text-extension set
  (`{.tex,.bib,.txt,.cls,.sty,.bst,.md,.markdown,.csv,.tsv,.json,.yml,.yaml,.xml,
  .svg,.tikz,.latex,.ltx,.def,.cfg,.gitignore,.bbx,.cbx}`) ⇒ **text**; everything
  in `allowed_extensions` but not text ⇒ **binary**; anything not in
  `allowed_extensions` ⇒ **skipped**.
- **Text decode:** try `utf-8`; on `UnicodeDecodeError` fall back to
  `utf-8` with `errors="replace"` after first trying `latin-1`
  (`cp1252`→`latin-1` order is acceptable; document the chosen order). Strip a
  leading UTF-8 BOM. Normalise CRLF/CR line endings to `\n`. The decoded string is
  what is stored as document content; enforce `max_document_bytes` on the
  encoded length.
- **Binary:** stored verbatim through `file_service`'s storage path; content-type
  is `sniff_content_type(head, declared=None)` and validated against the
  extension via `content_matches_extension` (spec 52). A binary whose sniffed
  type is disallowed (`allowed_upload_mime`) is **skipped** (recorded), not fatal.

#### 5.4.4 Root-doc detection & project naming

- Root doc: `detect_root_doc` (§5.2.3). If found, set `projects.root_doc_id` to
  that doc entity's id.
- Project name (when `name` form field is absent): derive from the root `.tex`'s
  `\title{...}` if present (a tiny regex over the decoded text, like Overleaf's
  `DocumentHelper.getTitleFromTexContent` — re-implemented, not copied), else the
  zip filename stem (sanitized via `sanitize_filename`), else `"Imported
  project"`. The name is set at project-create time in the endpoint (§5.2.1); the
  title-from-content refinement may instead be applied in the job (allowed — pick
  one and document it; simplest is filename-stem at create, no rename later).

### 5.5 Configuration

New env vars (added to `.env.example`, read via a settings mixin in
`config_groups.py`, following the existing upload/compile fields). Defaults chosen
to be safe and keep tests cheap:

| Env var | Setting field | Type | Default | Meaning |
|---------|---------------|------|---------|---------|
| `IMPORT_MAX_ZIP_BYTES` | `import_max_zip_bytes` | int | `52_428_800` (50 MiB) | max compressed upload size (streamed guard). |
| `IMPORT_MAX_UNCOMPRESSED_BYTES` | `import_max_uncompressed_bytes` | int | `314_572_800` (300 MiB) | max total uncompressed bytes across all kept entries. |
| `IMPORT_MAX_FILE_BYTES` | `import_max_file_bytes` | int | `52_428_800` (50 MiB) | max uncompressed size of any single entry. |
| `IMPORT_MAX_ENTRIES` | `import_max_entries` | int | `2_000` | max number of kept (folders+docs+files) entries. |
| `IMPORT_ALLOWED_EXTENSIONS` | `import_allowed_extensions` | list[str] (CSV/JSON, `NoDecode`) | `.tex,.bib,.cls,.sty,.bst,.bbx,.cbx,.txt,.md,.csv,.tsv,.json,.yml,.yaml,.xml,.svg,.tikz,.png,.jpg,.jpeg,.gif,.webp,.pdf,.eps` | extensions allowed in an imported archive (text ∪ binary). |
| `IMPORT_WORKDIR_ROOT` | `import_workdir_root` | str | `/tmp/inkstave-imports` | scratch dir for the temp zip copy (bounded, cleaned). |

Reuse `settings.max_document_bytes`, `settings.allowed_upload_mime`,
`settings.storage_stream_chunk_bytes`, and `settings.compile_queue_name`. Parse
the list fields with the existing `_parse_str_list` validator in `config.py`.

Also extend the `.env.example` comment block in the Storage/Compile section, next
to the existing `MAX_UPLOAD_BYTES` / `COMPILE_QUEUE_NAME` lines.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. All paths below were
> verified to exist in the cloned repo. Inkstave code must be written
> independently (MIT vs AGPLv3).

- `services/web/app/src/Features/Uploads/ArchiveManager.mjs` — **verified.** The
  zip-slip check (`_checkFilePath`: backslash→slash, reject `..` segments, reject
  un-normalised destinations), the "is zip too large?" pre-scan over the central
  directory before extraction (`_isZipTooLarge`, `MAX_UNCOMPRESSED_BYTES`,
  `maxEntitiesPerProject`), and ignored-file filtering. **Learn:** bound by
  declared sizes before decompressing; validate every path segment.
- `services/web/app/src/Features/Uploads/ProjectUploadManager.mjs` — **verified.**
  `createProjectFromZipArchive`: extract → find root doc
  (`ProjectRootDocManager.findRootDocFileFromDirectory`) → derive name from the
  tex title (`DocumentHelper.getTitleFromTexContent`) → create a blank project →
  initialise it with the contents → `setRootDocFromName` → delete the project on
  failure. **Learn:** the create-new-project-then-populate flow and root-doc/name
  derivation. (Inkstave creates the project up-front to return its id; see §5.2.1.)
- `services/web/app/src/Features/Uploads/FileTypeManager.mjs` — **verified.**
  Text-vs-binary determination and ignored-file rules. **Learn:** how a platform
  decides text vs binary (Inkstave uses an extension allow-list instead).
- `services/web/app/src/Features/Uploads/FileSystemImportManager.mjs` —
  **verified.** Walking the extracted tree and creating docs vs files.
  **Learn:** the folder/doc/file dispatch (Inkstave reuses its own
  `tree_service`/`document_service`/`file_service` instead).
- `services/web/app/src/Features/Uploads/ArchiveErrors.mjs` — **verified.**
  `InvalidZipFileError`, `EmptyZipFileError`, `ZipContentsTooLargeError`.
  **Learn:** the error taxonomy to surface to the client (Inkstave maps these to
  its own `ZipImportError` subclasses with `error_type`s).
- `services/web/app/src/Features/Uploads/ProjectUploadController.mjs` and
  `UploadsRouter.mjs` — **verified.** The multipart endpoint wiring. **Learn:**
  endpoint shape only.
- *No Overleaf equivalent for:* Inkstave's ARQ async-job + SSE status surface
  (Overleaf does this differently); that part follows Inkstave spec 22, not
  Overleaf.

## 7. Acceptance criteria

1. **Given** an authenticated user **when** they `POST /api/v1/projects/import`
   with a small valid `.zip` **then** the response is `202` with a body containing
   a NEW `project_id`, an `import_id`, and `status` in `{queued, running}`, and a
   new project exists owned by that user.

2. **Given** the import job runs to completion on a zip containing
   `main.tex` (with `\documentclass`), `chapters/intro.tex`, `refs.bib`, and
   `figures/diagram.png` **then** the new project's tree has a `chapters` folder, a
   `figures` folder, three doc entities with the decoded text content, one file
   entity whose blob bytes equal the PNG, and `projects.root_doc_id` points at the
   `main.tex` doc entity; the import status is `success`.

3. **Given** a zip whose central directory contains an entry named
   `../../etc/passwd` (or an absolute `/etc/passwd`, or `a/../../b`) **when**
   `plan_entries` runs **then** it raises `ZipSlipError` and **no** tree entity or
   blob is created for that archive (the import ends `failure` with
   `error_type="zip_slip"`).

4. **Given** a zip entry whose external attributes mark it a symlink **then**
   `plan_entries` raises `SymlinkEntryError` (`error_type="zip_symlink"`) and the
   target is never read or followed.

5. **Given** a zip whose declared uncompressed total exceeds
   `import_max_uncompressed_bytes`, **or** any single entry exceeds
   `import_max_file_bytes`, **or** the kept-entry count exceeds
   `import_max_entries` **then** the relevant error is raised
   (`ZipBombError` / `ZipEntryCountError`) **before any byte is decompressed**,
   and the import ends `failure` with the matching `error_type`.

6. **Given** the upload body exceeds `import_max_zip_bytes` while streaming
   **then** the endpoint returns `413 file_too_large` and the partial staged blob
   is deleted (no orphan in storage).

7. **Given** a file that is not a `.zip` (wrong extension or wrong magic bytes)
   **then** the endpoint returns `415 unsupported_media_type` and no project is
   created.

8. **Given** a text file encoded as `latin-1`/`cp1252` (non-UTF-8) **then** the
   imported document content is decoded without raising and is byte-for-byte
   round-trippable as text (no `UnicodeDecodeError` escapes the job), with BOM
   stripped and line endings normalised to `\n`.

9. **Given** a zip with a `.tex` containing `\documentclass` not named
   `main.tex`, plus a `main.tex` without `\documentclass` **then** root-doc
   detection selects the `\documentclass` file as `root_doc_id`. **And given** no
   `\documentclass` anywhere but a top-level `main.tex`, that `main.tex` is chosen.

10. **Given** a zip containing one disallowed-extension entry (e.g. `notes.exe`)
    among valid ones **then** that entry is **skipped** (not imported, no error),
    the import status is `partial`, and `entries_imported < entries_total`.

11. **Given** `GET /api/v1/projects/{project_id}/import/{import_id}` after the job
    finishes **then** it returns the terminal status and counts; the SSE
    `…/events` endpoint emits at least the running→terminal transitions.

12. **Frontend:** **given** the dashboard **when** the user clicks
    "Import project (.zip)", selects a tiny fixture zip, and submits **then** an
    upload-progress bar shows, the UI waits for the import, and on success it
    navigates to the new project's URL; on a rejected zip the dialog shows a
    friendly mapped error and stays open.

13. **Security regression:** a single unit test asserts that for a crafted
    malicious zip (zip-slip entry) **nothing** is written to the `ObjectStore` and
    **no** `tree_entities`/`documents`/`files` rows are created.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Heavy/real unzip is never exercised in the fast tier — only tiny in-memory zips.

- **Unit (pytest):**
  - `plan_entries` over in-memory zips (build with `zipfile.ZipFile` on a
    `io.BytesIO`): happy path; zip-slip (`..`, absolute, backslash, normalised);
    symlink entry (set `external_attr`); over-size total / per-file / entry-count
    (using **declared** sizes so no real big data is needed — set `file_size` via
    crafted `ZipInfo`); disallowed-extension skipping; empty-archive.
  - Encoding: latin-1/cp1252 bytes, BOM, CRLF normalisation; oversize-text skip.
  - `detect_root_doc`: `\documentclass` precedence, `main.tex` fallback,
    single-`.tex` fallback, none.
  - `reconstruct_tree` against a fake/in-memory `ObjectStore` and the test DB:
    asserts folders/docs/files created via the real services and correct
    `root_doc_id`.
- **Unit (Vitest):** `use-import-project` state machine (idle→uploading→
  processing→done/failed); `api.importProjectZip` builds the right `FormData`;
  `ImportProjectDialog` renders progress and maps `error_type`→message.
- **Integration (pytest + httpx + test DB + fake Redis/enqueuer):**
  - `POST /projects/import` with a tiny valid zip → `202`, project + import row
    created; with the fake enqueuer running the job **inline**, polling
    `GET …/import/{id}` returns `success` and the tree is correct end-to-end.
  - `413` (oversize via a low `import_max_zip_bytes` setting override) and `415`
    (non-zip) paths; staged blob cleaned up on `413`.
  - Defence-in-depth: import requested by a user who no longer owns the project →
    `error`.
- **E2E (Playwright):** with the worker/import mocked or run inline against a
  **tiny fixture zip** (one `main.tex` + one tiny PNG, a few hundred bytes):
  open the dashboard → "Import project (.zip)" → pick the fixture → submit →
  assert the new project opens (URL/title visible). No large archive; the import
  job either runs inline via the test enqueuer or the status is stubbed so the e2e
  stays fast.
- **Performance/budget note:** the fast tier uses only tiny in-memory zips and
  the inline fake enqueuer; the real ARQ worker and any large archive are out of
  the suite. `plan_entries` bounds everything by **declared** central-directory
  sizes, so a "bomb" test needs only a crafted `ZipInfo`, not real bytes. Per-test
  zips are < a few KB.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (model + migration, endpoint, status
      routes, reconstruction service, ARQ job + enqueuer + worker registration,
      schemas, config, frontend dialog/hook/api).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green (unit + integration + e2e).
- [ ] Full suite runs in **< 2 minutes** (verified; no real heavy unzip in the
      fast tier).
- [ ] Zip-slip, symlink, and zip-bomb protections are explicitly tested and
      reject **before** any extraction; nothing is written to storage/DB on
      rejection.
- [ ] Import **always** creates a new project; it never merges into an existing
      one.
- [ ] Lint/format/type-check clean (`ruff`, `mypy`/`pyright`; ESLint/Prettier).
- [ ] New env vars documented in `.env.example`; one ADR under `docs/` records the
      reporting channel (poll/SSE), the on-failure project disposition, and the
      text/binary classification rule.
- [ ] **No Overleaf code copied** — the unpack/reconstruction logic is an
      independent implementation.
