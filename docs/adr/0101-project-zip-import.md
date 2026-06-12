# ADR 0101 — Project import from a .zip archive

**Status:** accepted (spec 101) · **Phase:** Projects & file management

## Context

Users arriving from Overleaf/ShareLaTeX/a local `latexmk` tree need to bring a
project in. Import accepts a single `.zip`, **always creates a new project**, and
reconstructs its file tree (folders, text documents, binary files) by reusing the
existing `tree_service` / `document_service` / `file_service` / `ObjectStore`.
Unpacking is hardened against zip-slip and zip-bombs and runs off the request
thread. This records the non-obvious choices.

## Reporting channel: create-up-front + async job + poll/SSE

The upload endpoint (`POST /api/v1/projects/import`) does the cheap work
synchronously (extension/magic check, stream the body to a staged
`ObjectStore` blob under `imports/{uuid}/source.zip` with a size guard) and then,
in one transaction, **creates the new project**, inserts a `project_imports` row
(`status=queued`), and enqueues the `import_project_zip` ARQ job. It returns
`202` with the new `project_id` + `import_id` immediately, mirroring the spec-22
compile status surface (`project_imports` mirrors `compiles`). The frontend polls
`GET …/import/{import_id}` (and a parallel SSE `…/events` channel exists,
`services/import_stream.py`). The project id is returned up-front so the dashboard
can navigate straight to the new project.

## On-failure disposition: keep the (empty) project

If the async unpack fails (zip-slip / bomb / invalid / unexpected), the import
row goes `failure`/`error` but the **project is kept** (it may already hold the
root folder). This is the simplest behaviour consistent with returning a
`project_id` up-front; the UI surfaces the error and offers "delete the empty
project" (the existing spec-11 soft delete). Soft-deleting on hard failure was
considered and rejected as extra coupling for marginal benefit.

## Security: bound by the central directory, before decompressing

`plan_entries` validates the **central directory only** — it never decompresses
during validation. It rejects: absolute paths and `..`/`.` segments (zip-slip);
symlink entries (`S_IFLNK` in `external_attr`, never read or followed); and
enforces per-file / total-uncompressed / entry-count caps using the **declared**
sizes, so a bomb is refused before a single byte is inflated. Each segment is then
re-validated with the spec-12 `validate_name_segment` rules. `reconstruct_tree`
adds defence-in-depth: per-entry reads are capped at `IMPORT_MAX_FILE_BYTES` so a
lying header still cannot bomb the worker. Junk (`__MACOSX/`, `.DS_Store`,
`.git/`) is ignored silently.

## Text vs binary classification

Deterministic, by extension — no content sniffing for the *decision*. A fixed
text-extension set (`.tex/.bib/.cls/.sty/.md/.json/.yml/.svg/…`) ⇒ stored as
document text (spec 13); anything else that is in `IMPORT_ALLOWED_EXTENSIONS` ⇒
stored as a binary blob (spec 14, with the spec-52 sniff + extension/MIME
consistency check); anything else ⇒ **skipped** (recorded, status becomes
`partial`). Text is decoded UTF-8 → cp1252 → latin-1 (latin-1 never raises, so no
`UnicodeDecodeError` escapes), with a leading BOM stripped and CRLF/CR normalised
to `\n`.

## Root doc & project name

`detect_root_doc` picks the main `.tex`: first a `.tex` containing
`\documentclass` (shallowest path, ties broken by a `main.tex` basename then
lexicographically), else a top-level `main.tex`, else the only `.tex`, else none;
the job writes it to `projects.root_doc_id`. The project **name** is set once at
create time — the `name` form field, else the sanitized zip filename stem, else
`"Imported project"`. We deliberately do **not** derive the name from the `.tex`
`\title{}` (the simplest option; no later rename).

## Cleanup

The staged source blob and the temp zip copy (under `IMPORT_WORKDIR_ROOT`, needed
because `zipfile` requires a seekable file) are **always** removed in a `finally`.
The import is one-shot; the upload is not retained.

## Originality

The unpack/reconstruction logic is an independent implementation. Overleaf's
`ArchiveManager`/`ProjectUploadManager` were read for understanding only
(AGPLv3 vs Inkstave's MIT); no code was copied or translated.
