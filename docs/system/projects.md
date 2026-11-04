# Projects

A project is the container a user creates and works in: a name, an owner, a file tree, and the
documents and files hanging off that tree. This domain covers the project catalog (create, list,
rename, delete), the file tree (folders, documents and files as one table), and moving a whole project
in and out as a `.zip`. It comes from specs 11, 12, 15, 95, 101, 102 and 113. Document text and binary bytes
are in [documents.md](documents.md). Roles and capabilities (`access/`, `sharing/`) are in
[sharing.md](sharing.md).

## Where it is

The module is `backend/src/inkstave/modules/projects/`.

| File | Role |
|---|---|
| `backend/src/inkstave/modules/projects/__init__.py` | Public interface other modules may import |
| `backend/src/inkstave/modules/projects/catalog/service.py` | Project create, list, rename, soft delete, spell-check language; `ProjectNotFoundError` |
| `backend/src/inkstave/modules/projects/tree/service.py` | Tree create, rename, move, delete, `get_tree`, `ensure_root` |
| `backend/src/inkstave/modules/projects/tree/builder.py` | `compute_path`, `build_tree`: pure path and nesting helpers |
| `backend/src/inkstave/modules/projects/tree/safe_path.py` | `validate_name_segment`, the rules for one name |
| `backend/src/inkstave/modules/projects/tree/errors.py` | Tree error types |
| `backend/src/inkstave/modules/projects/routes/projects.py` | Catalog routes, permissions, zip export route, `PATCH .../settings` |
| `backend/src/inkstave/modules/projects/routes/tree.py` | Tree routes |
| `backend/src/inkstave/modules/projects/routes/project_import.py` | Zip import, its poll and SSE status routes |
| `backend/src/inkstave/modules/projects/deps.py` | `get_import_enqueuer` |
| `backend/src/inkstave/modules/projects/transfer/export.py` | Export plan and streaming zip writer |
| `backend/src/inkstave/modules/projects/transfer/jobs.py` | `import_project_zip` ARQ job |
| `backend/src/inkstave/modules/projects/transfer/enqueuer.py` | `ImportEnqueuer`, faked in tests |
| `backend/src/inkstave/modules/projects/transfer/repository.py` | `ProjectImportRepository` |
| `backend/src/inkstave/modules/projects/transfer/stream.py` | Redis pub/sub and SSE frames for import status |
| `backend/src/inkstave/modules/projects/transfer/zip_import/plan.py` | Central-directory validation, `TEXT_EXTENSIONS`, zip error types |
| `backend/src/inkstave/modules/projects/transfer/zip_import/reconstruct.py` | `reconstruct_tree`: archive to folders, docs and files |
| `backend/src/inkstave/modules/projects/transfer/zip_import/content.py` | `decode_text`, `detect_root_doc` |
| `backend/src/inkstave/worker.py` | Registers `import_project_zip` with `max_tries=1` |
| `frontend/src/routes/projects.tsx` | Project list route |
| `frontend/src/modules/projects/` | List page, dialogs, import dialog, download hook |
| `frontend/src/modules/file-tree/` | Tree panel, drag and drop, uploads |

Tests live in `backend/tests/integration/test_projects_api.py`,
`backend/tests/integration/test_project_service.py`, `backend/tests/integration/test_tree_api.py`,
`backend/tests/integration/test_tree_api_move.py`, `backend/tests/integration/test_tree_api_delete.py`,
`backend/tests/integration/test_project_import_api.py`,
`backend/tests/integration/test_project_import_job.py`,
`backend/tests/integration/test_project_export_api.py`, `backend/tests/unit/test_zip_import.py` and
`backend/tests/unit/test_safe_path.py`.

## Data

| Table | Key columns | Migration |
|---|---|---|
| `projects` | `owner_id`, `name`, `root_doc_id`, `deleted_at`, `spellcheck_language` | `backend/migrations/versions/20260609_1709_feb8f5c76b1a_create_projects.py`; `spellcheck_language` in `backend/migrations/versions/20261104_1200_4dd4cd5a3e49_spec113_spellcheck.py` |
| `tree_entities` | `project_id`, `parent_id`, `type`, `name`, `is_root` | `backend/migrations/versions/20260609_1722_8b301674ef53_create_tree_entities.py` |
| `project_imports` | `project_id`, `requested_by`, `status`, `source_key`, `source_bytes`, `job_id`, `entries_total`, `entries_imported`, `error_type`, `error_message`, `started_at`, `finished_at` | `backend/migrations/versions/20260612_1000_e2f4a8b13c90_create_project_imports.py` |

`tree_entities` is an adjacency list. `type` is `folder`, `doc` or `file`. Paths are never stored:
`compute_path` derives them from the ancestor chain, root excluded. The constraints are:

- `uq_tree_sibling_name`: unique `(parent_id, lower(name))`, so names are unique per folder and case-insensitively.
- `uq_tree_one_root_per_project`: at most one root per project.
- `root_has_no_parent`, `root_is_folder`, `name_not_empty_unless_folder`: the root is the only row with a NULL parent, is a folder, and is the only kind of row that may have an empty name.
- The self-FK on `parent_id` cascades, so deleting a folder removes its subtree. `documents` and `files` cascade from `tree_entities`.

"Parent must be a folder" is not expressible as a constraint. The service enforces it.

`projects.root_doc_id` holds a tree-entity id with no foreign key. `ix_projects_owner_active` is a
partial index on `(owner_id, updated_at DESC) WHERE deleted_at IS NULL`.

`project_imports.status` is `queued`, `running`, `success`, `partial`, `failure` or `error`. `failure`
is a rejected archive, `error` an unexpected fault. The last four are terminal.

Object storage holds the staged archive at `imports/{uuid}/source.zip` until the job ends. Import
also uses a scratch file at `{import_workdir_root}/{import_id}.zip`. Redis holds `cache:project:{id}`
(project metadata) and the pub/sub channel `project_import:events:{import_id}`.

## Routes

All paths are under `/api/v1`. Errors are the `{"error": {"type", "message", "details"}}` envelope;
the table gives `error.type`. Every route needs authentication. Project-scoped routes answer 404
`project_not_found` for a missing, deleted or non-member project, and 403 `insufficient_role` when the
caller's role lacks the capability. The capability column names the check.

| Method and path | Capability | What it does | Errors |
|---|---|---|---|
| `POST /projects` | any user | Create project, root folder, owner membership; optional `spellcheck_language` (default `en-US`) | 422 |
| `GET /projects` | any user | List projects the caller owns; `limit` 1 to 100, default 50, `offset` | 422 |
| `GET /projects/{project_id}` | `PROJECT_READ` | Read metadata, cached in Redis | 404 |
| `GET /projects/{project_id}/permissions` | member | Caller's role and capability codes | 404 |
| `PATCH /projects/{project_id}` | `PROJECT_WRITE` | Rename | 404, 403, 422 |
| `PATCH /projects/{project_id}/settings` | `DOC_WRITE` | Set `spellcheck_language` to `off`, `en-US` or `pt-BR`; editors may | 404, 403, 422 |
| `DELETE /projects/{project_id}` | `PROJECT_DELETE` | Soft delete, sweep compile outputs; 204 | 404, 403 |
| `GET /projects/{project_id}/export.zip` | `PROJECT_DOWNLOAD` | Stream the project as a zip | 404, 413 `export_too_large` |
| `POST /projects/import` | any user, `upload` rate limit | Stage a zip, create a new project, enqueue; 202 | 413 `file_too_large`, 415 `unsupported_media_type`, 429 |
| `GET /projects/{project_id}/import` | `PROJECT_READ` | Latest import of the project | 404 `import_not_found` |
| `GET /projects/{project_id}/import/{import_id}` | `PROJECT_READ` | One import | 404 `import_not_found` |
| `GET /projects/{project_id}/import/{import_id}/events` | member, via `sse_user` | SSE status stream | 404 |
| `GET /projects/{project_id}/tree` | `DOC_READ` | Nested tree | 404, 422 `tree_too_large` |
| `POST /projects/{project_id}/tree/entities` | `DOC_WRITE` | Create a `folder` or `doc` | 404 `parent_not_found`, 409 `name_conflict`, 422 `invalid_name`, `parent_not_a_folder` |
| `PATCH /projects/{project_id}/tree/entities/{entity_id}/rename` | `DOC_WRITE` | Rename | 404 `entity_not_found`, 409 `name_conflict`, `root_immutable`, 422 `invalid_name` |
| `PATCH /projects/{project_id}/tree/entities/{entity_id}/move` | `DOC_WRITE` | Reparent | 404 `entity_not_found`, `parent_not_found`, 409 `tree_cycle`, `name_conflict`, `root_immutable`, 422 `parent_not_a_folder` |
| `DELETE /projects/{project_id}/tree/entities/{entity_id}` | `DOC_WRITE` | Delete, recursive for folders; 204 | 404 `entity_not_found`, 409 `root_immutable` |

Owner holds every capability. Editors lack `PROJECT_WRITE`, `PROJECT_DELETE` and `PROJECT_SHARE`; they do hold
`DOC_WRITE`, which is why the spell-check language route is not `PROJECT_WRITE`.
Viewers have `PROJECT_READ`, `DOC_READ`, `FILE_READ` and `PROJECT_DOWNLOAD`, so a viewer can export.

## How it works

### Catalog

`create_project` inserts the row, calls `ensure_root` and adds the owner's `ProjectMembership`, all in
one transaction. `ProjectCreate` and `ProjectRename` strip the name and reject blanks; the database
also checks `name_not_blank`.

`get_project` is authorized first, then served from `RedisCache` under `project_meta_key`. Rename, delete
and the settings route invalidate the key. `rename_project` sets `updated_at = clock_timestamp()` so it advances even
inside one transaction.

### Delete

`delete_project` calls `soft_delete_project`, which sets `deleted_at`. It then invalidates the cache
and builds an `OutputStore` to call `delete_for_project`, which removes compile output blobs and rows.
Nothing else is removed. There is no purge job, no restore route and no trash. No code clears
`deleted_at` and nothing reads soft-deleted rows back to the user. The tree, documents and file blobs
stay in place indefinitely. The UI text is "Isso não pode ser desfeito."

### Cross-module imports

`backend/src/inkstave/modules/projects/routes/projects.py` is the one projects file that imports
upward in the module order. Both are declared exceptions in `backend/pyproject.toml`
(`[tool.importlinter]`, contract "module order, top to bottom"), each with a target to remove it:

- Line 17 imports `flush_open_project_docs` from `inkstave.modules.collab`; `export_project_zip` calls it at line 182.
- Line 18 imports `OutputRepository` and `OutputStore` from `inkstave.modules.compile`; `delete_project` uses them at lines 164 and 165.

### Tree

Every service call filters by `project_id` as well as the entity id. `create_entity` validates the
name, resolves the parent (`ensure_root` when `parent_id` is null), checks siblings case-insensitively,
inserts, and for a `doc` calls `ensure_document`. A flush `IntegrityError` also becomes `NameConflictError`,
which closes the race on the unique index. `file` entities are not creatable through the route; they
come from the upload path.

`validate_name_segment` strips whitespace and rejects empty names, more than 255 characters, `/` or
`\`, `.` and `..`, control characters, names ending in a dot or space, and Windows device names, bare
or as a stem (`con.txt`).

`move_entity` rejects the root, checks the new parent, uses `is_descendant` (a recursive CTE, `_subtree`)
to refuse a cycle, then checks for a sibling name clash at the destination. `delete_entity` collects
`File.storage_key` over the subtree, deletes the row (cascade does the rest), then deletes each blob.

`get_tree` fetches at most `tree_max_nodes + 1` rows and raises `TreeTooLargeError` over the cap.
`build_tree` sorts folders first, then by lower-cased name. Tree mutation routes call `get_tree` again
in `_read` to compute the returned `path`.

### Zip export

`export_project_zip` runs in this order, so that a 413 is a clean response and not a broken stream:

1. `flush_open_project_docs` writes open CRDT rooms to `documents.content`. A failed room flush is logged and skipped.
2. `build_export_plan` loads the tree and bulk-reads document sizes and file keys. It rejects a total over `export_max_total_bytes` and sorts by path segments, so a folder precedes its contents.
3. `read_doc_contents` reads all document text into memory.
4. The route returns a `StreamingResponse` over `stream_project_zip`.

The request session is closed before the body streams, which is why text is read first.
`stream_project_zip` writes with stdlib `zipfile` into `_StreamBuffer`, drained as it fills, and streams
blobs chunk by chunk. Each entry has a fixed 1980 timestamp and fixed permissions. A blob missing from
storage is logged and left out. `zip_filename_for` and `content_disposition` build a safe attachment
header with ASCII and RFC 5987 forms.

### Zip import

`import_project` always creates a new project. It never merges into an existing one.

1. The extension must be `.zip`. The declared type must be a zip type, or the first chunk must start with the `PK\x03\x04` magic. Otherwise 415.
2. `_stage_upload` streams to object storage, enforcing `import_max_zip_bytes`. On overflow the staged key is deleted and the route answers 413.
3. `_create_import` creates the project (`_effective_name`: the form name, else the sanitized file stem, else `Imported project`), the `project_imports` row, then enqueues. On any failure the staged blob is deleted.
4. The route answers 202 with `ProjectImportRead`.

The job `import_project_zip` wraps `_import_once`. It loads the row, returns at once if terminal, and
re-checks ownership with `_still_owned`. It then marks `running` and calls `_import_archive`:

1. `_stage_to_temp` copies the blob to a seekable file, re-checking the size.
2. `plan_entries` validates the central directory without decompressing. A symlink, absolute path, `.` or `..` segment, or any segment failing `validate_name_segment` rejects the whole archive. `__MACOSX`, `.git` and `.DS_Store` are dropped silently. Entries with a disallowed extension count as skipped. Caps use declared sizes.
3. `reconstruct_tree` creates folders on demand and walks the entries. Text entries go through `_read_member_bounded`, `decode_text` (BOM stripped, UTF-8 then cp1252 then latin-1, line endings normalised) and `set_content_from_collab`. Binary entries are sniffed, then go through `upload_file`. A rejected binary, or a text entry over `max_document_bytes`, is skipped.
4. `detect_root_doc` prefers a `.tex` containing `\documentclass` (shallowest, then `main.tex`, then lexical), then a top-level `main.tex`, then the only `.tex`. `_process_archive` writes it to `root_doc_id`.

Status is `success` when `docs + files == entries + skipped`, otherwise `partial`. A `ZipImportError`
rolls back and ends `failure`; any other exception rolls back and ends `error`. Both leave the empty
project behind, and the frontend offers "Excluir o projeto vazio". `_cleanup` always removes the staged
blob and scratch file. `settle` commits and publishes to Redis at each transition; `sse_stream`
subscribes before sending its snapshot so no transition is lost.

## Rules and guarantees

| Rule | Test |
|---|---|
| A non-member gets 404 with no body data, never 403 | `backend/tests/integration/test_projects_api.py::test_ownership_is_existence` |
| A soft-deleted project is not reachable through `get_owned_project` | `backend/tests/integration/test_project_service.py::test_soft_delete_hides_project` |
| Listing excludes deleted projects and orders by recency | `backend/tests/integration/test_project_service.py::test_list_excludes_deleted_and_orders_by_recency` |
| Rename strictly advances `updated_at` | `backend/tests/integration/test_project_service.py::test_rename_bumps_updated_at` |
| A new project has a root folder | `backend/tests/integration/test_tree_api.py::test_root_auto_created` |
| Tree routes hide other users' projects | `backend/tests/integration/test_tree_api_delete.py::test_ownership_isolation` |
| Sibling names are unique case-insensitively | `backend/tests/integration/test_tree_api.py::test_duplicate_name_is_case_insensitive_conflict` |
| A parent from another project is 404 on create | `backend/tests/integration/test_tree_api.py::test_create_under_other_project_parent_is_404` |
| A parent from another project is 404 on move | `backend/tests/integration/test_tree_api_move.py::test_move_to_cross_project_parent_is_404` |
| A folder cannot move into its own subtree; a parent must be a folder | `backend/tests/integration/test_tree_api_move.py::test_move_cycle_and_non_folder` |
| The root cannot be renamed, moved or deleted | `backend/tests/integration/test_tree_api_delete.py::test_root_is_immutable` |
| Deleting a folder removes its subtree | `backend/tests/integration/test_tree_api_delete.py::test_delete_recursive` |
| Deleting a file entity through the tree removes its blob | `backend/tests/integration/test_tree_api_delete.py::test_delete_via_tree_api_removes_blob` |
| Unsafe names are rejected | `backend/tests/unit/test_safe_path.py::test_invalid_names` |
| Export has a fixed order, timestamps and complete content | `backend/tests/integration/test_project_export_api.py::test_export_returns_zip_with_complete_ordered_tree` |
| Two exports have the same names and entry contents (compared by entry, not by archive bytes) | `backend/tests/integration/test_project_export_api.py::test_export_is_deterministic` |
| Export reads text after the CRDT flush | `backend/tests/integration/test_project_export_api.py::test_exports_flushed_current_content` |
| Over the export cap gives 413 | `backend/tests/integration/test_project_export_api.py::test_size_cap_returns_413` |
| A missing blob is skipped, not a 500 | `backend/tests/integration/test_project_export_api.py::test_missing_blob_is_skipped_not_500` |
| Export then import reproduces the tree | `backend/tests/integration/test_project_export_api.py::test_export_import_round_trip` |
| Import creates a new project and enqueues | `backend/tests/integration/test_project_import_api.py::test_import_returns_202_and_creates_new_project` |
| An oversized upload leaves no staged blob and no job | `backend/tests/integration/test_project_import_api.py::test_import_oversize_413_and_no_orphan_blob` |
| Zip-slip paths are rejected at plan time | `backend/tests/unit/test_zip_import.py::test_plan_rejects_zip_slip` |
| A zip-slip archive creates no entities and no blobs | `backend/tests/integration/test_project_import_job.py::test_zip_slip_writes_nothing` |
| Symlink entries are rejected | `backend/tests/unit/test_zip_import.py::test_plan_rejects_symlink` |
| Declared sizes are capped before decompression | `backend/tests/unit/test_zip_import.py::test_plan_rejects_oversize_total_before_decompress` |
| Entry count is capped | `backend/tests/unit/test_zip_import.py::test_plan_rejects_too_many_entries` |
| A disallowed extension is skipped, not fatal | `backend/tests/unit/test_zip_import.py::test_plan_skips_disallowed_extension_not_fatal` |
| A skipped entry ends `partial` | `backend/tests/integration/test_project_import_job.py::test_import_partial_when_entry_skipped` |
| The job re-checks ownership and ends `error` if lost | `backend/tests/integration/test_project_import_job.py::test_ownership_defence_marks_error` |
| A decompressed entry over its limit is stopped by `_read_member_bounded` | no dedicated test |

## Spell-check language

Spec 113. `projects.spellcheck_language` is `off`, `en-US` or `pt-BR`, with a check constraint, and
existing rows get `en-US`. `ProjectRead` returns it; `ProjectCreate` accepts it, so the client sends the creator's
interface language. The check itself runs in the browser (see `docs/system/frontend.md`, Spell check); the server
only stores the choice and never sees the text.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `TREE_MAX_NODES` | `50000` | Row cap on `get_tree` |
| `CACHE_ENABLED` | `true` | Project metadata cache |
| `CACHE_TTL_SECONDS` | `30` | TTL of that cache |
| `IMPORT_MAX_ZIP_BYTES` | `52428800` | Compressed archive cap |
| `IMPORT_MAX_UNCOMPRESSED_BYTES` | `314572800` | Sum of declared sizes of kept entries |
| `IMPORT_MAX_FILE_BYTES` | `52428800` | One entry, declared and decompressed |
| `IMPORT_MAX_ENTRIES` | `2000` | Kept leaf entries |
| `IMPORT_ALLOWED_EXTENSIONS` | list in `backend/src/inkstave/core/config/groups.py` | JSON array or comma-separated |
| `IMPORT_WORKDIR_ROOT` | `/tmp/inkstave-imports` | Scratch directory |
| `EXPORT_MAX_TOTAL_BYTES` | `209715200` | Sum of document and file bytes |
| `EXPORT_ASYNC_ENABLED` | `false` | See below |
| `RATE_LIMIT_UPLOAD` | `60/60` | Policy on `POST /projects/import` |
| `COMPILE_QUEUE_NAME` | `compiles` | Import shares this ARQ queue |
| `COMPILE_SSE_KEEPALIVE_S` | `15` | Import SSE keep-alive |

## Points of attention

- `GET /projects` filters on `owner_id`. A collaborator's accepted projects do not appear, and `frontend/src/modules/projects/api.ts` has no other list call.
- Import is exposed to a race. `_create_import` enqueues before the unit of work commits. A worker that picks the job up first finds no row, returns, and with `max_tries=1` the row stays `queued` and the staged blob stays. No test covers this, since tests use a fake enqueuer.
- A case-only clash between text entries (`A.tex`, `a.tex`) is not handled. `_import_text` lets `NameConflictError` escape, so the whole import ends `error`. The same clash for binaries is a skip.
- In `_ensure_folder`, when a path segment clashes with an existing non-folder, `_find_child_folder` returns `None`, and `None` means root. Entries below it land in the project root.
- A rollback in `_import_archive` drops rows, but blobs already written by `upload_file` stay as orphans.
- When `_still_owned` fails, the job settles without reaching `_import_archive`, so `_cleanup` never runs and the staged blob stays.
- `.eps` is in `IMPORT_ALLOWED_EXTENSIONS` but always skipped. It has no magic signature, `_import_binary` passes no declared type, and `application/octet-stream` is not in `allowed_upload_mime`. An archive with EPS figures ends `partial`.
- `_import_binary` treats an `upload_file` rejection as a skip, but the entity is already flushed and nothing rolls it back. The default lists never reach this path. Adding an import extension absent from `UPLOAD_ALLOWED_EXTENSIONS` leaves a `file` entity with no `files` row.
- A reserved or unsafe name anywhere in an archive (`con.tex`) rejects the whole archive as `zip_slip`, even though it is not a traversal.
- `IMPORT_MAX_ENTRIES` counts leaf entries only, though its comment says folders too. `TEXT_EXTENSIONS` wins over `IMPORT_ALLOWED_EXTENSIONS`, so removing `.tex` from the setting changes nothing.
- `EXPORT_ASYNC_ENABLED=true` does not start a job. No async path exists; the flag only disables the 413, so the export streams regardless of size. Its comment in `backend/src/inkstave/core/config/groups.py` promises an ARQ artifact.
- `BodySizeLimitMiddleware` in `backend/src/inkstave/core/http/body_limit.py` caps `/import` at `MAX_UPLOAD_BYTES`. Raising `IMPORT_MAX_ZIP_BYTES` above it has no effect.
- `EXPORT_MAX_TOTAL_BYTES` is larger than the import caps, so a large export may not re-import. A round trip also changes kinds: a `.tex` or `.svg` stored as a `file` comes back a `doc`, and a `doc` with no extension is skipped.
- Export is streamed by the server, but all document text is in memory first, and `downloadProjectZip` buffers the whole archive in the browser.
- `root_doc_id` is only written by the import job. No route sets it, it has no FK, deleting that document leaves it dangling, and the frontend does not read it. The compile entry point comes from the compile request's `main_file`.
- The import job writes `root_doc_id` without invalidating `cache:project:{id}`. A read during the job can pin a null value for up to `CACHE_TTL_SECONDS`. Rename and delete invalidate before the commit, so a concurrent read can also re-cache the old value.
- `projects.updated_at` moves on rename and on the import job's `root_doc_id` update. Document and tree edits do not touch it, so the "Última modificação" sort is not last edit time.
- `tree_max_nodes` is enforced on read only. `create_entity` has no cap, but the route's `_read` calls `get_tree`, so a create that crosses the cap fails 422 and rolls back. Service-level callers are not stopped.
- `move_entity` takes no lock, so two concurrent moves can pass `is_descendant` and form a cycle detached from the root.
- `routes/tree.py`'s module docstring and `catalog/service.py` still describe owner scoping. Tree routes now use capabilities. Rename and delete pass `PROJECT_WRITE` or `PROJECT_DELETE` and then re-check through `get_owned_project`; only the owner holds those, so the two agree.
- ADR 0011 `docs/adr/0011-project-delete.md` promises a purge job in a later spec. It was never built.
