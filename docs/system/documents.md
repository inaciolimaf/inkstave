# Documents and files

A project's tree holds two kinds of content. A document is UTF-8 text the editor works on, stored in
PostgreSQL with an integer version. A file is a binary such as an image or PDF, stored in object
storage with its metadata in PostgreSQL. This domain covers the document content API and its
optimistic concurrency, the autosave contract the editor follows over REST, binary upload and
download, and the storage backends. It comes from specs 13, 14 and 19. The tree that owns these rows is
in [projects.md](projects.md). Live editing is in [collab.md](collab.md).

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/modules/projects/content/documents.py` | `replace_content`, `ensure_document`, the collab seam |
| `backend/src/inkstave/modules/projects/content/files.py` | `upload_file`, `open_file_content`, `delete_file`, `sniff_content_type` |
| `backend/src/inkstave/modules/projects/content/uploads.py` | `sanitize_filename`, extension and content-match checks |
| `backend/src/inkstave/modules/projects/models/document.py` | `Document` |
| `backend/src/inkstave/modules/projects/models/file.py` | `File` |
| `backend/src/inkstave/modules/projects/routes/documents.py` | Document routes |
| `backend/src/inkstave/modules/projects/routes/files.py` | File routes |
| `backend/src/inkstave/modules/projects/schemas/document.py` | `DocumentContentRead`, `DocumentContentReplace` |
| `backend/src/inkstave/modules/projects/schemas/file.py` | `FileRead` |
| `backend/src/inkstave/infra/storage/` | Object storage package |
| `backend/src/inkstave/infra/storage/base.py` | `ObjectStore`, `ObjectStat`, `ObjectNotFoundError` |
| `backend/src/inkstave/infra/storage/local.py` | `LocalObjectStore` |
| `backend/src/inkstave/infra/storage/s3.py` | `S3ObjectStore` |
| `backend/src/inkstave/infra/storage/factory.py` | `get_object_store(settings)` picks the backend |
| `backend/src/inkstave/infra/deps.py` | FastAPI dependency, overridden in tests |
| `backend/src/inkstave/core/http/body_limit.py` | `BodySizeLimitMiddleware` |
| `frontend/src/modules/editor/autosave/use-document-autosave.ts` | The autosave state machine |
| `frontend/src/modules/editor/autosave/types.ts` | `SaveStatus`, timing constants |
| `frontend/src/modules/editor/api.ts` | `getDocument`, `saveDocument`, `VersionConflictError` |
| `frontend/src/modules/editor/conflict-dialog.tsx` | Conflict resolution dialog |
| `frontend/src/modules/editor/save-status-indicator.tsx` | Save status |
| `frontend/src/modules/editor/unsaved-changes-guard.tsx` | `beforeunload` guard |
| `frontend/src/modules/file-tree/use-uploads.ts` | Upload progress and name-conflict prompt |

Tests live in `backend/tests/integration/test_documents_api.py`,
`backend/tests/integration/test_document_service.py`, `backend/tests/integration/test_files_api.py`,
`backend/tests/integration/test_files_api_validation.py`,
`backend/tests/integration/test_files_api_access.py`, `backend/tests/unit/test_storage.py` and
`frontend/src/modules/editor/autosave/use-document-autosave.test.ts`.

## Data

| Table | Columns | Migration |
|---|---|---|
| `documents` | `entity_id` (PK, FK), `project_id`, `content`, `version`, `size_bytes` | `backend/migrations/versions/20260609_1732_bec8287c4664_create_documents.py` |
| `files` | `entity_id` (PK, FK), `project_id`, `storage_key`, `content_type`, `size_bytes`, `checksum_sha256`, `original_filename` | `backend/migrations/versions/20260609_1748_be53747ebcf5_create_files.py` |

Both are 1:1 satellites of `tree_entities`, keyed by the entity id, and cascade when the entity goes.
`project_id` is denormalised for project-wide queries; the services keep it consistent.
`documents.version` starts at 0. `size_bytes` is the UTF-8 byte length. `files.storage_key` is unique.

The file blob key is `projects/{project_id}/files/{entity_id}`. Keys are server-generated. Other
domains use the same store for their own keys: imports use `imports/{uuid}/source.zip`, and compile
outputs and history have theirs. With the local backend, objects live under `file_storage_local_path`.

## Routes

All paths are under `/api/v1`. Errors are the `{"error": {"type", "message", "details"}}` envelope;
the table gives `error.type`. Every route needs authentication, and also answers 404
`project_not_found` for a non-member or missing project and 403 `insufficient_role` for a role without
the capability.

| Method and path | Capability | What it does | Errors |
|---|---|---|---|
| `GET /projects/{project_id}/documents/{entity_id}` | `DOC_READ` | Content, version, size, `updated_at` | 404 `entity_not_found`, 409 `not_a_document` |
| `PUT /projects/{project_id}/documents/{entity_id}` | `DOC_WRITE` | Replace content, body `{content, base_version}` | 404 `entity_not_found`, 409 `not_a_document`, `version_conflict`, 413 `content_too_large`, `payload_too_large` |
| `POST /projects/{project_id}/files` | `FILE_WRITE`, `upload` rate limit | Multipart: `file`, optional `parent_id`, `name`; 201 | 404 `parent_not_found`, 409 `name_conflict`, 413 `file_too_large`, 415 `unsupported_media_type`, 422 `invalid_name`, `parent_not_a_folder`, 429 |
| `GET /projects/{project_id}/files/{entity_id}` | `FILE_READ` | Metadata | 404 `entity_not_found`, 409 `not_a_file` |
| `GET /projects/{project_id}/files/{entity_id}/content` | `FILE_READ` | Stream bytes, `Content-Disposition: inline` | 404 `entity_not_found`, `file_blob_missing`, 409 `not_a_file` |
| `DELETE /projects/{project_id}/files/{entity_id}` | `FILE_WRITE` | Delete entity and blob; 204 | 404 `entity_not_found`, 409 `not_a_file` |

`version_conflict` carries `details[0].current_version` and `details[0].current_content`, so the
client can resolve without another request. Viewers have the read capabilities only.

## How it works

### Document content

`get_document` resolves the entity through `tree_service.get_entity` with `expected_type=doc`. It
creates an empty row through `ensure_document` if one is missing, so a read may insert.

`replace_content` runs its checks in this order: entity type, size against `max_document_bytes`, then a
single statement:

`UPDATE documents SET content, version = base_version + 1, size_bytes, updated_at WHERE entity_id = ? AND version = ?`

There is no row lock. A stale `base_version`, older or newer than the row, matches zero rows, and the
service raises `VersionConflictError` with the row's current state. The version bumps on every
successful PUT, even if the content is unchanged.

### The collab seam

`read_content_for_collab` and `set_content_from_collab` are exported from
`backend/src/inkstave/modules/projects/__init__.py`. Live editing and zip import use them.
`set_content_from_collab` writes with no version check, is a no-op when the text is unchanged, bumps
`version` by one on a real change, and inserts the row if absent (`version` 1). It does not check
`max_document_bytes`. `documents.content` is the text that compile, export and other readers see, and
`flush_open_project_docs` brings it up to date before those reads.

### Autosave contract

`useDocumentAutosave` is the REST client of this API. States are `clean`, `dirty`, `saving`, `error`,
`offline` and `conflict`.

1. It seeds `baseVersion`, `serverText` and `localText` from the fetched document, once per document id.
2. An edit marks `dirty` and arms a debounce of `DEBOUNCE_MS` (1000). Blur, tab hide, the `online` event and Ctrl/Cmd+S flush at once.
3. `flush` sends the whole text with `base_version`. It skips when text matches `serverText` and is single-flight through `savingRef`. Edits arriving mid-save re-flush on the next tick.
4. On success, `version` becomes the new `baseVersion`.
5. On 409, status is `conflict`, and flushes stop until the user chooses. `resolveKeepMine` rebases on `current_version` and re-saves. `resolveReload` takes the server text.
6. Other failures retry after `RETRY_BACKOFF_MS` (1, 2, 4, 8 seconds). Past `MAX_RETRIES` it stops at `error` with a manual retry. If the browser is offline, status is `offline`.
7. Leaving a document fires one last `saveDocument` for unsaved text.

`hasUnsaved` is any status other than `clean`, and feeds the `beforeunload` guard.

This path applies only when collaboration is off. `editor-pane.tsx` takes `collabEnabled` from
`COLLAB_ENABLED`, which is `Boolean(config.collabWsUrl)`. With collab active, `CollabEditor` receives
text over the WebSocket, the save indicator is hidden, and `onLocalChange` is never called, so the hook
sends nothing.

### Upload

The `POST` route computes `sanitize_filename(name or file.filename or "file")`: it keeps the final path
component, replaces everything outside `[A-Za-z0-9._ -]` with `_`, and drops leading dots. So
traversal is stripped, not rejected. `upload_file` then:

1. Calls `create_entity` for a `file`, which runs `validate_name_segment`, parent checks and the sibling check.
2. Checks `extension_allowed` against `upload_allowed_extensions`. Failure is 415.
3. Reads the first chunk, and `_validated_content_type` sniffs it. PNG, JPEG, GIF, WebP and PDF are recognised by signature; anything else falls back to the client's declared type. The type must be in `allowed_upload_mime`, and `content_matches_extension` must hold.
4. Calls `store.put` with `_hashing_body`, which replays the first chunk, hashes SHA-256 off the event loop, and raises `FileTooLargeError` past `max_upload_bytes`.
5. Inserts the `File` row.

The entity is flushed before the checks, so rejections rely on the unit of work rolling it back. Any
failure at or after step 4 also deletes the blob key.

`BodySizeLimitMiddleware` runs first. Paths ending in `/files` or `/import` get `max_upload_bytes`;
everything else gets `max_request_body_bytes`.

### Download and delete

`open_file_content` loads the row, opens the blob, and turns `ObjectNotFoundError` into 404
`file_blob_missing`. The route sets `Content-Length` from the row. `delete_file` confirms the type, then
calls `delete_entity` with the store, which deletes the row and then the blob.

### Object storage

`ObjectStore` has `put`, `stat`, `delete`, `exists` and `open`, plus `get` and `read_range` built on
`open`. A missing key raises `ObjectNotFoundError` on `stat` and `open`. `delete` on a missing key is
not an error.

`LocalObjectStore` resolves keys under the base directory and raises `ValueError` for a key that
escapes it. `put` writes to `{name}.tmp-{uuid}` then `os.replace`, removing the temp file on failure.
Blocking I/O runs in threads. `read_range` seeks instead of reading from the start.

`S3ObjectStore` uses aioboto3 and works with S3 or MinIO. `open` issues the GET and returns
`_stream_body`, which holds the client open until the stream ends and yields `chunk_size` chunks.
`client_config` sets the connect and read timeouts and two total attempts. Not-found is recognised by
code (`NoSuchKey`, `NotFound`, `404`) or HTTP 404. `Settings` refuses `file_storage_backend=s3` with an
empty bucket.

`get_object_store` in `backend/src/inkstave/infra/storage/factory.py` imports the S3 backend lazily.
Routes receive the store through `backend/src/inkstave/infra/deps.py`, and the ARQ worker builds its own
in `backend/src/inkstave/worker.py`.

## Rules and guarantees

| Rule | Test |
|---|---|
| A new doc has empty content at version 0 | `backend/tests/integration/test_documents_api.py::test_new_doc_has_empty_content` |
| Each replace raises the version by one and updates size | `backend/tests/integration/test_document_service.py::test_replace_increments_version_and_size` |
| A stale version is 409 with server state, and leaves the row unchanged | `backend/tests/integration/test_documents_api.py::test_stale_version_conflicts_with_server_state` |
| A base version ahead of the row is also a conflict | `backend/tests/integration/test_document_service.py::test_replace_with_base_version_greater_than_current_conflicts` |
| Two saves from one base: one wins, one gets 409 (run sequentially) | `backend/tests/integration/test_documents_api.py::test_no_lost_update` |
| Truly concurrent replaces cannot both succeed | no dedicated test; relies on the single `UPDATE` |
| Oversized content is rejected | `backend/tests/integration/test_document_service.py::test_content_too_large` |
| A folder or file is not a document | `backend/tests/integration/test_documents_api.py::test_non_doc_entity_is_conflict` |
| Other users cannot read or replace | `backend/tests/integration/test_documents_api.py::test_ownership_isolation` |
| Deleting the entity removes the content row | `backend/tests/integration/test_documents_api.py::test_delete_entity_cascades_content` |
| Collab flush writes text into `documents.content` | `backend/tests/integration/test_collab_manager.py::test_flush_bridges_text_to_spec13` |
| `set_content_from_collab` is a no-op on equal text and bumps version on change | no dedicated test |
| Upload then download is byte-identical, under the per-project key | `backend/tests/integration/test_files_api.py::test_upload_then_download_roundtrip` |
| Over the upload limit is 413 and leaves no tree entity | `backend/tests/integration/test_files_api_validation.py::test_size_limit` |
| A disallowed type is 415 | `backend/tests/integration/test_files_api_validation.py::test_disallowed_mime` |
| Bytes must match the extension | `backend/tests/integration/test_files_api_validation.py::test_upload_content_extension_mismatch_is_415` |
| A traversal name is reduced to its basename | `backend/tests/integration/test_files_api_validation.py::test_upload_traversal_filename_is_sanitized_and_stored_safely` |
| A reserved name is 422 and stores nothing | `backend/tests/integration/test_files_api_validation.py::test_upload_reserved_name_is_rejected` |
| A duplicate name is 409 | `backend/tests/integration/test_files_api_access.py::test_duplicate_name` |
| Deleting removes entity and blob | `backend/tests/integration/test_files_api.py::test_delete_removes_entity_and_blob` |
| A blob gone from storage is 404 `file_blob_missing` | `backend/tests/integration/test_files_api.py::test_blob_missing_download` |
| Local writes are temp then atomic replace | `backend/tests/unit/test_storage.py::test_local_put_writes_temp_then_replaces_atomically` |
| A key cannot escape the local base directory | `backend/tests/unit/test_storage.py::test_local_rejects_traversal_key` |
| Local reads stream in chunks | `backend/tests/unit/test_storage.py::test_local_streams_in_chunks` |
| Delete of a missing key is idempotent, on both backends | `backend/tests/unit/test_storage.py::test_local_missing_and_delete`, `backend/tests/unit/test_storage.py::test_s3_roundtrip_and_notfound` |
| The S3 backend requires a bucket | `backend/tests/unit/test_storage.py::test_s3_requires_bucket` |
| S3 GET does not buffer the object | no dedicated test; the fake store test only checks round-trip bytes |
| Autosave debounces, is single-flight, retries with a cap, and resolves conflicts | test cases in `frontend/src/modules/editor/autosave/use-document-autosave.test.ts` |

## Settings

| Variable | Default | Effect |
|---|---|---|
| `MAX_DOCUMENT_BYTES` | `2000000` | Limit on REST replace and on imported text |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Global cap for non-upload paths |
| `MAX_UPLOAD_BYTES` | `52428800` | Upload cap, streamed; also the middleware cap on upload paths |
| `UPLOAD_ALLOWED_EXTENSIONS` | list in `backend/src/inkstave/core/config/groups.py` | JSON array or comma-separated |
| `ALLOWED_UPLOAD_MIME` | same file | JSON array or comma-separated |
| `RATE_LIMIT_UPLOAD` | `60/60` | Policy on `POST` files and import |
| `FILE_STORAGE_BACKEND` | `local` | `local` or `s3` |
| `FILE_STORAGE_LOCAL_PATH` | `./data/files` | Base directory |
| `STORAGE_STREAM_CHUNK_BYTES` | `65536` | Read and sniff chunk size |
| `S3_BUCKET` | empty | Required for `s3` |
| `S3_REGION` | `us-east-1` | |
| `S3_ENDPOINT_URL` | empty | For MinIO and similar |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | empty | Empty uses the default AWS credential chain |
| `S3_CONNECT_TIMEOUT_S`, `S3_READ_TIMEOUT_S` | `5`, `30` | Client timeouts |

## Points of attention

- **`PUT` strips the document.** `DocumentContentReplace` extends `StrictModel`, which sets `str_strip_whitespace=True`, so `content` loses leading and trailing whitespace, including the final newline. `"  a\n\n"` is stored as `"a"`. The client then records `serverText` as the unstripped text it sent, so it does not notice. No test covers it.
- **The autosave branch is not reached in a normal build.** `collabWsUrl` falls back to a derived URL, so `COLLAB_ENABLED` is always true. `useDocumentAutosave`, the conflict dialog and the save indicator run only in tests or for a deployment that changes this constant. ADR 0019 describes them as the working baseline.
- **REST and an open room do not coordinate.** `replace_content` does not touch CRDT state. Once a document has CRDT state with text, `_load` in `backend/src/inkstave/modules/collab/rooms/manager.py` ignores `documents.content`, and a later flush overwrites the REST write. An API client calling `PUT` loses its edit silently if the document has been opened in collab.
- `MAX_REQUEST_BODY_BYTES` (1 MiB) is below `MAX_DOCUMENT_BYTES` (2 MB), and `/documents/` paths get the JSON cap. A REST save of over about 1 MiB is 413 from the middleware, and `content_too_large` is only reachable below that.
- The middleware's 413 uses `{"error": {"code": "payload_too_large", ...}}`, with `code` where everything else has `type`.
- Postgres `text` cannot hold a NUL. Neither `replace_content` nor `decode_text` removes one, so a `\u0000` in a PUT, or in an imported text entry, fails at the database rather than as a typed error.
- `S3ObjectStore.put` joins the whole stream into memory before `put_object`, so the streaming guarantee holds for S3 reads only. A 50 MB upload is held in full. There is no multipart upload. The size cap still applies, since the join runs the guarded generator.
- `delete_entity` removes blobs before the transaction commits. A failed commit leaves rows pointing at deleted blobs. `store.delete` is not wrapped despite the "best-effort" comment, so a storage error fails the request partway through.
- Soft-deleting a project removes no file blobs. See [projects.md](projects.md).
- After a document switch, a save already in flight is not checked against the current document id. When it resolves it patches `baseVersion` and `serverText` onto the next document's state. The result is a spurious save or conflict. The final save on leaving a document uses `.catch(() => {})`, so a failed last save is lost with no signal.
- The upload conflict prompt cannot work. `onReplaceConflict` re-sends the same name, and the backend has no overwrite, so "Substituir" always gets a second `name_conflict`.
- `sanitize_filename` is ASCII-only. `Café.png` is stored as `Caf_.png`, while tree rename accepts Unicode.
- The download header writes the name raw into `filename="..."`, with no RFC 5987 form. Starlette encodes headers as latin-1, so a file renamed to a name outside latin-1 makes the download fail with a server error. Export's `content_disposition` handles this.
- For content with no signature, the client's declared type is what gets checked and stored. Browsers typically send a type outside `ALLOWED_UPLOAD_MIME` for `.csv` and `.eps`, or none for `.tex`, `.cls` and `.sty`, so these allowed extensions usually get 415 unless declared `text/plain`.
- An uploaded `.tex` that does pass becomes a `file` entity, not a `doc`, and cannot be edited.
- ADR `docs/adr/0014-object-storage.md` says streams are accepted on write and cites pre-move paths such as `storage/base.py`. The code path is `backend/src/inkstave/infra/storage/`, and the S3 write buffers as above.
