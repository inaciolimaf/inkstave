# ADR 0023 — Compile output storage, range serving & retention

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 23 — Compile Output Storage & Retrieval

## Context

Spec 22 left an output-persistence hook as a stub. This spec makes compile
outputs durable (via the spec-14 storage abstraction), serves the PDF (with HTTP
range support for PDF.js) and the log, and bounds storage with a retention sweep.

## Decisions

### 1. `compile_outputs` table + deterministic key layout

A per-artifact row (`name`, `kind`, `content_type`, `size_bytes`, `storage_key`,
`etag`) keyed to `compile_id`. Bytes go through the **spec-14 `ObjectStore`**
under a flat, bulk-deletable layout `compiles/{project_id}/{compile_id}/{name}`.
`kind` is classified by name (`pdf`/`log`/`synctex`/`aux`/`other`). The `etag` is
the **sha256 hex** of the bytes (for HTTP `ETag` + future dedup). Indexes:
`(compile_id)`, `(project_id, created_at)`, unique `(compile_id, name)`.

### 2. The job owns the workdir; persist before terminal

To avoid a workdir-lifetime race, the **job** invokes spec-21 with
`keep_workdir=True`, then — **before** publishing the terminal status event —
calls the persist hook (read artifact bytes → put into storage → upsert rows),
then calls `cleanup_workdir(result.workdir)`. A persistence failure sets the
compile `status=error` with a clear message but never crashes the worker. The
hook signature is `(session, compile_id, project_id, result)` so it writes in the
job's transaction; the worker wires the real `OutputStore`.

### 3. Range-capable PDF serving

`GET …/output.pdf` honours HTTP semantics:
- no `Range` → **200** with `Content-Type: application/pdf`, `Content-Length`,
  `Accept-Ranges: bytes`, `ETag`, `Cache-Control: private, max-age=…`,
  `Content-Disposition: inline`.
- `Range: bytes=a-b` → **206** with `Content-Range` and exactly the slice
  (a pure `parse_range` helper handles explicit/open/suffix ranges + clamping).
- unsatisfiable range → **416** with `Content-Range: bytes */<total>`.
- matching `If-None-Match` → **304**.

The size/etag/content-type come from the recorded row (no extra `stat`). Ranges
are served by a new **`ObjectStore.read_range`**: a default stream-and-slice in
the base, with a seeking override on `LocalObjectStore` (avoids reading the whole
object). The log is streamed as `text/plain; charset=utf-8`.

### 4. Retention sweep (ARQ cron)

`cleanup_compile_outputs` runs hourly. `list_compiles_for_retention` (a window
function) selects compiles **beyond the per-project keep window**
(`COMPILE_RETAIN_PER_PROJECT`) **or older than** `COMPILE_RETENTION_MAX_AGE_S`,
that still hold outputs, oldest-first, bounded by `COMPILE_RETENTION_BATCH`. For
each it deletes the storage objects **and** the `compile_outputs` rows but keeps
the `compiles` status row for history (so a pruned compile isn't reselected).

### 5. Project deletion sweeps storage

Projects are **soft-deleted** (no FK cascade fires), so the project `DELETE`
endpoint calls `OutputStore.delete_for_project` to remove the storage objects and
output rows explicitly.

## Consequences

- New module pieces in `compile/` (`outputs.py`, `output_repository.py`,
  `retention.py`); migration for `compile_outputs`; `ObjectStore.read_range`
  added to spec 14. New settings (`COMPILE_OUTPUT_PREFIX`, `COMPILE_RETAIN_*`,
  `COMPILE_RETENTION_*`, `COMPILE_PDF_CACHE_MAX_AGE_S`).
- Spec 24 (preview UI) fetches `/output.pdf` (range) and `/output.log`; spec 26
  reads the stored `.synctex.gz`; spec 27 reads the full `.log`.
- Tests use a temp-dir disk backend + synthetic `CompileResult`s (files on disk);
  no real compiles.

## Alternatives considered

- **Content-addressed dedup across compiles** — out of scope; the etag is stored
  to enable it later.
- **A zip-of-all-outputs endpoint** — optional/not a DoD item; deferred.
- **Reading the whole object to serve a range** — kept as the base default for
  arbitrary backends, but `LocalObjectStore` seeks for true partial reads.
