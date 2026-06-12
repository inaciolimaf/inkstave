# ADR 0014 — Object storage: abstraction, key scheme, blob lifecycle

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 14 — Binary file storage

## Context

Inkstave stores binary assets (images, PDFs, `.bib`, …) that link to `file`
tree-entities. The compiler (21–23) and PDF preview (24) will fetch bytes
through the same abstraction. We need a backend-agnostic store with a local
default (Alpine-light, dev) and an optional S3-compatible backend, without
coupling the rest of the app to either.

## Decisions

### 1. A small async `ObjectStore` interface + factory/DI

`storage/base.py` defines `ObjectStore` (`put`/`get`/`open`/`delete`/`exists`/
`stat`) returning/accepting **streams**; `ObjectNotFoundError` is the single
not-found signal (mapped to `404`). `storage/factory.get_object_store(settings)`
picks the backend from `FILE_STORAGE_BACKEND` and is wired as a FastAPI
dependency, so routes/services receive an `ObjectStore` and **tests override it
with a fake**. The service/router are entirely backend-agnostic — proven by
running the integration suite over both the `local` backend and an in-memory
fake (AC10), with no network.

### 2. Two backends

- **`LocalObjectStore`** (default) — objects under a resolved base dir; the final
  path must stay inside it (traversal defence even though keys are
  server-generated). Writes go to a temp file then `os.replace` (atomic); reads
  stream in chunks; blocking I/O runs in a thread (`asyncio.to_thread`) so the
  event loop is not stalled; `delete` of a missing key is a no-op.
- **`S3ObjectStore`** — `aioboto3` (async; never a sync client on the loop).
  Honours `S3_ENDPOINT_URL` (MinIO/S3-compatible), bucket, region, credentials;
  translates `NoSuchKey`/404 to `ObjectNotFoundError`; `delete` is idempotent.
  **Limitation (accepted):** GET buffers the object in memory within the client
  context (the default `local` backend streams). A streaming S3 download can be
  added later if large S3-backed assets become common.

### 3. Key scheme — `projects/{project_id}/files/{file_id}`

`file_id` is the `files` row id, which is the `file` tree-entity id (the PK).
This keeps keys **per-project** (a project's blobs are trivially enumerable for a
future purge job) and globally collision-free without being guessable in a way
that matters (access is always auth + ownership gated; downloads are proxied,
not via pre-signed URLs). The `sha256` checksum is stored in the DB for integrity
and future dedup, but the **key uses the row id** so it is stable across
re-uploads to the same entity.

### 4. Blob lifecycle vs. the DB (not transactional)

Object storage is not part of the DB transaction:

- **Upload:** create the entity + `files` row inside the transaction, stream the
  blob to the store; on **any** failure after `put`, best-effort `store.delete`
  the key so no orphan blob survives the rolled-back entity. Size limit
  (`MAX_UPLOAD_BYTES`) and MIME allow-list (`ALLOWED_UPLOAD_MIME`) are enforced
  **while streaming** — the size check aborts early past the limit (`413`) rather
  than buffering the whole upload to count.
- **Delete (and spec-12 tree delete):** the DB row is removed in the transaction
  (the self-FK cascade removes subtrees), then blob keys are deleted
  **best-effort** after the flush. To avoid orphan blobs when a folder subtree
  containing files is deleted, **spec 12's `delete_entity` now takes an
  `ObjectStore`**: it collects the file storage keys in the subtree (recursive
  CTE) before the cascade and deletes those blobs afterward. A periodic
  orphan-blob reaper (ARQ) is out of scope.

### 5. Content-type & integrity

The effective content type is sniffed from magic bytes (PNG/JPEG/GIF/WebP/PDF)
with a fall back to the client-declared type, then checked against the allow-list
(so a declared-but-disallowed type like `application/x-dosexec` is rejected
`415`). `sha256` and byte size are computed in a single streaming pass.

## Consequences

- New runtime deps: `aioboto3` (S3), `python-multipart` (FastAPI uploads).
- New `files` table (1:1 with a `file` entity), `storage/` package, settings
  (`FILE_STORAGE_*`, `MAX_UPLOAD_BYTES`, `ALLOWED_UPLOAD_MIME`,
  `STORAGE_STREAM_CHUNK_BYTES`, `S3_*`), all documented in `.env.example`.
- Settings validate that `S3_BUCKET` is set when the backend is `s3`.
- The "ownership = existence" rule (404) is inherited from spec 11/12.

## Alternatives considered

- **Pre-signed S3 URLs for download** — efficient, but leaks bucket details and
  bypasses the API's auth/ownership gate; rejected (downloads are proxied).
- **Storing blobs as DB bytea** — simple but bloats the DB and the hot tables;
  rejected for an object store.
- **Content-addressed keys (`sha256`)** — enables cross-project dedup but makes
  re-upload/rename semantics and per-project purge harder; rejected for the
  stable per-entity key (dedup can be layered on later using the stored checksum).
- **`moto` for S3 tests** — `aiobotocore` bypasses moto's sync HTTP patching;
  rejected in favour of an in-memory fake for parity + a mocked client for the
  `S3ObjectStore` translation logic (no network, fast).
