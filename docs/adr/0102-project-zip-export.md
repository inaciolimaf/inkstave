# ADR 0102 — Project export as a streaming .zip

**Status:** accepted (spec 102) · **Phase:** Projects & file management

## Context

Users need to take a whole project out of Inkstave — every folder, document (at
its current text), and binary file — as a single `.zip`. This is the export half
of project portability and the round-trip counterpart of spec 101 (import).

## Sync streaming, not an async artifact

The endpoint `GET /api/v1/projects/{id}/export.zip` builds the archive
**synchronously** and returns a `StreamingResponse`. The archive is produced by
an async generator (`stream_project_zip`) that writes through stdlib
`zipfile.ZipFile` into a small drain-as-you-go buffer (`_StreamBuffer`): after
each entry — and, for binary files, after each storage chunk — the generator
yields and clears the buffer. Memory stays O(chunk + one entry header) regardless
of project size, so no full-archive buffering and no separate ARQ job / artifact
storage is needed for normal projects.

A size cap (`EXPORT_MAX_TOTAL_BYTES`, default 200 MiB over the sum of doc + file
bytes) is enforced in `build_export_plan` **before** any bytes stream; over it,
the endpoint returns `413 export_too_large`. An optional async-artifact path
(`EXPORT_ASYNC_ENABLED`) is reserved but **not implemented** in this spec — the
sync path + the 413 cap satisfy the requirements.

## No `EXPORT_STREAM_CHUNK_BYTES`

The builder reuses the existing `storage_stream_chunk_bytes` (default 64 KiB) to
pump file bytes and decide when to drain the buffer. A separate export-only chunk
knob would be unused noise, so it was **not** added (the spec explicitly allows
reusing the storage knob).

## Determinism

Entries are sorted by their **segment list** (`path.split("/")`), so a folder
("a") always precedes its contents ("a/b.tex") — plain string ordering would not
guarantee that. Every entry gets a fixed `ZipInfo.date_time` of the zip epoch
(1980-01-01) and a fixed external-attr/compression mode, so the archive is
reproducible given the same tree. Tests assert entry **names + per-entry
uncompressed content**, not raw archive bytes (DEFLATE output is zlib-dependent).

## Current text via the CRDT flush

Before reading `documents.content`, the route calls
`flush_open_project_docs(request.app.state.collab, …)` — the same best-effort
materialisation the compile enqueue uses — so exported text reflects live,
unsaved-to-column edits. Rooms open on another instance are skipped.

## Authorization & resilience

A dedicated `PROJECT_DOWNLOAD` capability (granted to owner/editor/viewer) gates
the route via the existing `require_capability`; a non-member gets the same `404`
the rest of the project API returns. A `file` entity whose blob is missing from
storage is **skipped with a logged warning**, never a 500 — one orphaned blob
must not fail a large export.

## Originality

The streaming-zip and Content-Disposition approaches are independently
implemented with stdlib `zipfile`; Overleaf's archiver-based
`ProjectZipStreamManager`/`ProjectDownloadsController` were read for understanding
only (AGPLv3 vs Inkstave's MIT).
