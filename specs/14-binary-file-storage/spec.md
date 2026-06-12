# Spec 14 — Binary file storage (requirements)

## 1. Summary

This spec adds **binary file** support: uploading images, PDFs, `.bib` and other
non-text assets, storing their bytes through a pluggable storage abstraction
(`put`/`get`/`delete`/`stat`, streaming), and linking each blob to a `file`
tree-entity (spec 12). Two backends are provided: **local filesystem** (default,
Alpine-light, dev) and **S3-compatible** (optional, configured by env). Endpoints
cover multipart upload (with size/type limits) and authenticated streaming
download.

## 2. Context & dependencies

- **Depends on:** **12** (`tree_entities`, type `file`, ownership scoping, path
  safety), **13** (satellite-row pattern), **11/02/03/04/08**.
- **Unlocks:**
  - **17** — file-tree UI upload/download.
  - **21–23** — the compiler fetches binary assets via the storage interface.
  - **24** — PDF preview may stream output (separate output storage in 23, but the
    same abstraction style).
- **Affected areas:** backend (storage package, model, schemas, service, router,
  migration), infra (local upload dir, optional S3 env), docs (ADR).

## 3. Goals

- A storage abstraction `ObjectStore` with `put`/`get`/`delete`/`stat`/`exists`,
  **streaming** for get and put, and a clean async interface.
- Two implementations: `LocalObjectStore` (filesystem) and `S3ObjectStore`
  (S3-compatible, e.g. AWS S3 / MinIO), chosen by env via a factory + DI.
- A `files` table (1:1 with a `file` tree entity) holding storage key, MIME type,
  size, checksum, original filename.
- `POST` multipart upload endpoint that creates the `file` entity (or attaches to
  one) and stores bytes; size + MIME allow-list limits.
- `GET` download endpoint streaming bytes with auth and correct headers.
- `DELETE` removes the `file` entity and its blob.
- Alembic migration; unit + integration tests with a **fake S3** (no network);
  suite < 2 min.

## 4. Non-goals (explicitly out of scope)

- Image conversion/optimisation/thumbnails (Overleaf has this; out of scope).
- Serving assets into the compile sandbox (specs 21–23 consume the interface).
- Compile **output** storage — PDF/log/synctex (spec 23 has its own model, may
  reuse this abstraction).
- Frontend upload UI / drag-and-drop (spec 17).
- Versioning of binary files, deduplication across projects, virus scanning,
  signed/pre-signed temporary URLs (download is proxied through the API here).

## 5. Detailed requirements

### 5.1 Storage abstraction

Package `app/storage/` (independent of any Overleaf code).

**Interface `ObjectStore` (`app/storage/base.py`, `abc.ABC`, async):**

```
async def put(self, key: str, data: AsyncIterator[bytes] | bytes, *,
              content_type: str | None = None) -> ObjectStat
async def get(self, key: str) -> AsyncIterator[bytes]          # streams; raises ObjectNotFound
async def open(self, key: str) -> tuple[ObjectStat, AsyncIterator[bytes]]  # stat + stream in one call
async def delete(self, key: str) -> None                        # idempotent (no error if absent)
async def exists(self, key: str) -> bool
async def stat(self, key: str) -> ObjectStat                    # raises ObjectNotFound

ObjectStat: size: int, content_type: str | None, etag/checksum: str | None
```

- `ObjectNotFound` is a storage-layer exception mapped to `404` at the API.
- Streaming: `get`/`open` must not load the whole object into memory; chunk size
  configurable (default 64 KiB). `put` accepts a byte stream from the upload.

**Backends:**

- **`LocalObjectStore` (`app/storage/local.py`)** — stores objects under a base
  directory (`FILE_STORAGE_LOCAL_PATH`). The key maps to a path **safely**: the
  base dir is resolved (`Path.resolve()`), the final path must remain inside it
  (reject traversal — defence in depth even though keys are server-generated).
  Writes go to a temp file then `os.replace` (atomic). `delete` of a missing file
  is a no-op. Creates parent dirs as needed.
- **`S3ObjectStore` (`app/storage/s3.py`)** — uses an async S3 client
  (`aioboto3`/`aiobotocore` — pick one and pin it; do **not** introduce a sync
  client blocking the event loop). Honours `S3_ENDPOINT_URL` (for MinIO/
  S3-compatible), bucket, region, credentials. Maps S3 `NoSuchKey`/404 to
  `ObjectNotFound`. `delete` treats missing-key as success.

**Factory + DI (`app/storage/factory.py`):**

- `get_object_store(settings) -> ObjectStore` returns the configured backend based
  on `FILE_STORAGE_BACKEND` (`local` | `s3`). Wired as a FastAPI dependency so
  routes/services receive an `ObjectStore` and tests can override it with a fake.

**Key scheme (content-addressed per project).** Storage key:
`projects/{project_id}/files/{file_id}` where `file_id` is the `files` row id.
This keeps keys per-project (easy to enumerate/purge a project later) and avoids
guessable/global collisions. The checksum (sha256) is stored in the DB for
integrity but the key uses the row id (stable across re-uploads to the same
entity). Record this in `docs/adr/0014-object-storage.md`.

### 5.2 Data model

#### Table `files`

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `entity_id` | `UUID` | **PK**, FK → `tree_entities.id` `ON DELETE CASCADE` | 1:1 with a `file` tree entity. |
| `project_id` | `UUID` | `NOT NULL`, FK → `projects.id` `ON DELETE CASCADE` | Denormalised for scoping/purge. |
| `storage_key` | `VARCHAR(512)` | `NOT NULL` | Key in the object store (see scheme). |
| `content_type` | `VARCHAR(255)` | `NOT NULL` | Detected/declared MIME type. |
| `size_bytes` | `BIGINT` | `NOT NULL`, `CHECK (size_bytes >= 0)` | Stored byte length. |
| `checksum_sha256` | `CHAR(64)` | `NOT NULL` | Hex sha256 of bytes (integrity / future dedup). |
| `original_filename` | `VARCHAR(255)` | `NULL` | As provided by the client (sanitised; informational). |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()` | |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL` default `now()`, `onupdate now()` | Bumped on re-upload. |

**Constraints / invariants:**

- `entity_id` must reference a `tree_entities` row of `type = 'file'` (enforced in
  service; tested).
- A `files` row exists **iff** its tree entity is a `file`; deleting the entity
  cascades the row (and the service deletes the blob — see below).
- `UNIQUE(storage_key)`.

**Indexes:** PK on `entity_id`; `ix_files_project_id` on `(project_id)`;
unique `uq_files_storage_key` on `(storage_key)`.

**Relationships:** `File.entity` ↔ `TreeEntity` (1:1, back-ref `TreeEntity.file`);
`File.project` → `Project`.

**Blob lifecycle vs. DB.** Blob deletion is **not** transactional with the DB.
On delete: remove the DB row inside the transaction, then best-effort delete the
blob after commit (idempotent `store.delete`). If the entity is deleted via the
tree cascade (spec 12), a background reconciliation is **out of scope**; instead,
the tree-delete service path for a `file` entity must call `store.delete` for the
blob (i.e. spec 12's delete, when it removes a `file`, invokes the storage delete
through this spec's service). Document this coupling.

**Migration:** one Alembic revision creating `files` with constraints and indexes.
No backfill (no pre-existing files). Reversible.

### 5.3 Backend / API

Router `app/api/v1/files.py`, mounted under `/api/v1/projects/{project_id}`.
**All routes require auth** + spec-11 ownership (`404 project_not_found` otherwise).

**Schemas (`app/schemas/file.py`):**

```
FileRead:
    entity_id: UUID
    project_id: UUID
    name: str                 # tree entity name
    content_type: str
    size_bytes: int
    checksum_sha256: str
    original_filename: str | None
    created_at: datetime
    updated_at: datetime
```

#### Endpoints

| # | Method | Path | Auth | Body | Success | Response |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `POST` | `/api/v1/projects/{project_id}/files` | required | multipart: `file` (the binary), `parent_id` (UUID, optional → root), `name` (optional → derived from upload filename) | `201` | `FileRead` |
| 2 | `GET` | `/api/v1/projects/{project_id}/files/{entity_id}` | required | — | `200` | `FileRead` (metadata) |
| 3 | `GET` | `/api/v1/projects/{project_id}/files/{entity_id}/content` | required | — | `200` | streamed bytes (`StreamingResponse`) |
| 4 | `DELETE` | `/api/v1/projects/{project_id}/files/{entity_id}` | required | — | `204` | empty |

**Behaviour details:**

1. **Upload (POST)** —
   - Validate `name` (or the upload filename) with the **same** `safe_path`
     validator from spec 12 (single segment, no traversal, reserved-name check).
   - Resolve `parent_id` (default root); must be a `folder` in this project
     (else `422 parent_not_a_folder` / `404 parent_not_found`).
   - Enforce **size limit** `MAX_UPLOAD_BYTES` while streaming (do not buffer the
     whole file to count; abort early past the limit → `413`).
   - Enforce **MIME allow-list** `ALLOWED_UPLOAD_MIME` (configurable; default a
     sensible set: images `image/png|jpeg|gif|webp|svg+xml`, `application/pdf`,
     `text/plain`, `application/x-bibtex`/`text/x-bibtex`, `application/octet-stream`
     as a fallback off by default). Reject disallowed → `415 unsupported_media_type`.
     Detect content type from the magic bytes / declared type; prefer sniffing.
   - Create the `file` tree entity (type `file`) under the parent — reusing spec 12
     create logic, including **duplicate sibling name → 409**. If a `file` entity
     of that name already exists and the request targets re-upload, the simplest
     rule for this spec: **reject duplicates with 409** (no implicit overwrite);
     overwrite-by-name is out of scope.
   - Compute sha256 and size while streaming to the store; `put` the bytes under
     the key `projects/{project_id}/files/{file_id}`; insert the `files` row.
   - Wrap entity+row creation in the DB transaction; perform the blob `put` and, on
     any DB failure after `put`, best-effort delete the blob (no orphan). Return
     `201 FileRead`.
2. **Get metadata** — returns `FileRead` for the `file` entity.
3. **Download content** — streams the blob via `store.open(key)` as a
   `StreamingResponse` with `Content-Type` from the row, `Content-Length` from
   `size_bytes`, and `Content-Disposition: inline; filename="<name>"`
   (sanitised). `404` if the blob is missing in the store (`ObjectNotFound`) even
   though the row exists (surface as `file_blob_missing`).
4. **Delete** — removes the `files` row + `file` tree entity (transaction), then
   best-effort deletes the blob. `204`.

**Error cases:**

| Condition | Status | `error.code` |
| --- | --- | --- |
| No/invalid token | `401` | `unauthorized` |
| Project missing/not owned/soft-deleted | `404` | `project_not_found` |
| Entity not found / not a `file` | `404` / `409` | `entity_not_found` / `not_a_file` |
| Parent not found / not a folder | `404` / `422` | `parent_not_found` / `parent_not_a_folder` |
| Invalid name (path safety) | `422` | `invalid_name` |
| Duplicate sibling name | `409` | `name_conflict` |
| Upload exceeds size limit | `413` | `file_too_large` |
| Disallowed MIME | `415` | `unsupported_media_type` |
| Blob missing in store on download | `404` | `file_blob_missing` |
| Malformed multipart / bad UUID | `422` | `validation_error` |

**Service layer (`app/services/file_service.py`):**

- `upload_file(session, store, project_id, parent_id, name, upload_stream,
  declared_content_type) -> File` — streaming hash+size+limit, MIME check,
  entity+row creation, blob put, rollback-with-cleanup.
- `get_file(session, project_id, entity_id) -> File`.
- `open_file_content(session, store, project_id, entity_id) -> (ObjectStat | File, AsyncIterator[bytes])`.
- `delete_file(session, store, project_id, entity_id) -> None`.

### 5.4 Real-time / jobs / external integrations

- **External:** S3-compatible object storage when `FILE_STORAGE_BACKEND=s3`. In
  tests, the S3 backend is exercised against an **in-memory/faked** S3 (e.g.
  `moto` in non-network mode, or a hand-rolled fake implementing `ObjectStore`) —
  **no real network**, to honour the 2-minute budget. The default backend in CI is
  `local`.
- No ARQ jobs in this spec. (A future orphan-blob reaper could be an ARQ job; out
  of scope.)

### 5.5 Configuration

New settings (add all to `.env.example` with defaults):

| Env var | Default | Meaning |
| --- | --- | --- |
| `FILE_STORAGE_BACKEND` | `local` | `local` \| `s3`. |
| `FILE_STORAGE_LOCAL_PATH` | `./data/files` | Base dir for `LocalObjectStore`. |
| `MAX_UPLOAD_BYTES` | `52428800` (50 MB) | Per-file upload size limit. |
| `ALLOWED_UPLOAD_MIME` | (the default set above, comma-separated) | MIME allow-list. |
| `STORAGE_STREAM_CHUNK_BYTES` | `65536` | Streaming chunk size. |
| `S3_ENDPOINT_URL` | (empty) | Custom endpoint for MinIO/S3-compatible. |
| `S3_REGION` | `us-east-1` | S3 region. |
| `S3_BUCKET` | (empty) | Bucket name (required when backend is `s3`). |
| `S3_ACCESS_KEY_ID` | (empty) | Credential (or use instance role). |
| `S3_SECRET_ACCESS_KEY` | (empty) | Credential. |

Validation: when `FILE_STORAGE_BACKEND=s3`, `S3_BUCKET` (and credentials unless an
ambient role is used) must be set; the settings model raises on startup otherwise.

## 6. Overleaf reference (study only — never copy)

> Inkstave's `ObjectStore` is an independent abstraction. Study the *shape* of
> Overleaf's persistor and filestore controller; write your own.

- `services/filestore/app/js/FileController.js` — upload/get/delete HTTP handlers,
  streaming, size handling. Informs our router contracts.
- `services/filestore/app/js/LocalFileWriter.js` — writing an upload safely to
  local disk (temp file then move). Informs `LocalObjectStore`.
- `libraries/object-persistor/src/AbstractPersistor.js` — the persistor interface
  (sendStream/getObjectStream/deleteObject/getObjectSize). Informs `ObjectStore`.
- `libraries/object-persistor/src/FSPersistor.js` — filesystem backend approach.
- `libraries/object-persistor/src/S3Persistor.js` — S3 backend approach and how
  endpoint/credentials are configured.
- `libraries/object-persistor/src/PersistorFactory.js` — backend selection by
  config; informs our `get_object_store` factory and the "404 fallback" idea
  (treat NoSuchKey as `ObjectNotFound`).

## 7. Acceptance criteria

1. **Given** an owner and a project, **when** they `POST` a small PNG to `/files`,
   **then** `201` with `FileRead` (correct `content_type`, `size_bytes`,
   64-hex `checksum_sha256`), a `file` tree entity appears in the tree, and the
   blob exists in the configured store under the per-project key.
2. **Given** the uploaded file, **when** the owner `GET`s `/files/{id}/content`,
   **then** `200` streamed bytes byte-for-byte equal to the original, with correct
   `Content-Type` and `Content-Length`.
3. **Given** a file larger than `MAX_UPLOAD_BYTES`, **when** uploaded, **then**
   `413 file_too_large`, no tree entity and no blob are left behind.
4. **Given** a disallowed MIME (e.g. an `.exe`/`application/x-dosexec` when not in
   the allow-list), **when** uploaded, **then** `415 unsupported_media_type`.
5. **Given** a name like `../evil` or `a/b`, **when** uploaded, **then**
   `422 invalid_name`; nothing stored.
6. **Given** a parent that is a `doc`/`file` (not a folder), **when** uploading
   under it, **then** `422 parent_not_a_folder`.
7. **Given** a sibling with the same name exists, **when** uploading, **then**
   `409 name_conflict`.
8. **Given** an uploaded file, **when** the owner `DELETE`s it, **then** `204`, the
   tree entity is gone, and the blob is removed from the store.
9. **Given** the `files` row exists but the blob was removed out-of-band, **when**
   downloading, **then** `404 file_blob_missing`.
10. **Given** `FILE_STORAGE_BACKEND=s3` with a **faked** S3, all of the above
    upload/download/delete behaviours pass identically (backend-agnostic) — proving
    the abstraction. With `local`, the same suite passes. No real network is used;
    suite stays under 2 minutes.
11. User B accessing user A's project files → `404 project_not_found`.
12. The migration applies/rolls back cleanly creating `files` with its constraints
    and indexes.

## 8. Test plan

> S3 is faked/in-memory; local writes go to a tmp dir fixture. No network.

- **Unit (pytest):**
  - `LocalObjectStore`: put/get/stat/exists/delete round-trip; streaming chunks;
    traversal-key rejection; delete-missing is a no-op; atomic write (temp→replace).
  - `S3ObjectStore` against a fake/moto: same round-trip; NoSuchKey→`ObjectNotFound`;
    delete-missing success.
  - `factory.get_object_store` selects backend per settings; s3 settings validation.
  - Streaming hash+size+limit helper: counts bytes, aborts past limit, computes
    sha256 correctly (multi-chunk).
- **Integration (pytest + httpx + Postgres, store overridden with fake/local):**
  - Upload happy path → 201, tree entity + row + blob; download byte-equality.
  - Size limit 413; MIME 415; bad name 422; non-folder parent 422; dup name 409.
  - Delete removes row, entity, blob; download-after-delete 404.
  - Blob-missing download → 404.
  - Cross-user → 404.
  - Run the **same** integration tests parametrised over `local` and faked `s3`
    backends to prove abstraction parity.
  - Migration up/down smoke.
- **E2E (Playwright):** none (UI is spec 17).
- **Performance/budget note:** test files are a few KB; the size-limit test uses a
  small configured limit (override `MAX_UPLOAD_BYTES` to e.g. 1 KB in that test)
  rather than a real 50 MB payload. S3 is in-memory. Expected added runtime: small.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (storage interface + 2 backends + factory,
      model, service, router, migration).
- [ ] All acceptance criteria in §7 pass (including backend-parity).
- [ ] All tests in §8 written and green; S3 path mocked, no network.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] All new env vars documented in `.env.example`; ADR
      `docs/adr/0014-object-storage.md` records the key scheme.
- [ ] Spec-12 `file`-entity delete path wired to delete the blob (no orphan).
- [ ] No Overleaf code copied.
