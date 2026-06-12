# Spec 23 — Compile Output Storage & Retrieval (requirements)

## 1. Summary

This spec makes compile outputs durable and retrievable. When a compile finishes,
the spec-22 ARQ job hands the `CompileResult` (artifacts on the workdir) to an
**output-persistence service** that copies each artifact (PDF, `.log`,
`.synctex.gz`, and other aux files) into the **spec-14 storage abstraction**,
keyed by `compile_id`/`project_id`, recording a per-artifact metadata row. It
adds **authenticated endpoints** to list a compile's outputs, **stream the PDF**
(correct content type + HTTP **range requests** for incremental PDF.js loading),
and **stream the log** as text. It defines a **retention/cleanup policy** (keep
the latest N per project / expire by age) implemented as an ARQ cron-style job.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 22** — the `compiles` table, the `CompileResult` artifact manifest,
    and the **output-persistence hook** in `run_compile` (a stub in spec 22 that
    this spec implements).
  - **Spec 14** — the `Storage` abstraction (disk + S3-compatible backends),
    used to put/get/delete artifact bytes and to stream ranges.
  - **Spec 02** — settings, errors, ARQ worker bootstrap, Redis.
  - **Spec 08** — `current_user` + project authorization.
- **Unlocks:**
  - **Spec 24** — preview UI fetches the PDF and log from here.
  - **Spec 26** — reads the stored `.synctex.gz`.
  - **Spec 27** — reads the stored full `.log`.
- **Affected areas:** backend (`backend/app/compile/outputs.py`,
  `output_api.py`, `output_repository.py`, retention job), DB migration, storage
  layout, `.env.example`, docs.

## 3. Goals

- A `OutputStore` service that persists every `CompileArtifact` of a finished
  compile into spec-14 storage under a deterministic key layout and records
  metadata rows.
- Wire it into spec-22's `run_compile` (replacing the stub) so persistence
  happens before the terminal status event is published.
- Endpoints: list outputs, stream the PDF (range-capable), stream the log.
- Retention/cleanup: bounded number of retained compiles per project + age-based
  expiry, deleting both storage objects and metadata, as an ARQ job.
- Correct **content types**, `Content-Length`, `Accept-Ranges`, conditional/range
  responses, and `ETag` for caching.

## 4. Non-goals (explicitly out of scope)

- PDF rendering / preview pane / zoom — spec 24.
- Parsing `.synctex.gz` or the `.log` — specs 26/27.
- A downloadable ZIP of all outputs (nice-to-have; may be added later, not
  required here). If trivially cheap you MAY add a single zip endpoint, but it is
  not a Definition-of-Done item.
- Output content-addressed caching / dedup across compiles.

## 5. Detailed requirements

### 5.1 Data model

New table **`compile_outputs`** (Alembic migration):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `UUID` PK | |
| `compile_id` | `UUID` FK → `compiles.id` | `ON DELETE CASCADE`, indexed. |
| `project_id` | `UUID` FK → `projects.id` | denormalised for cleanup queries, indexed. |
| `name` | `text` | e.g. `output.pdf`, `main.log`, `main.synctex.gz`. |
| `rel_path` | `text` | path within the compile output set. |
| `kind` | `text` (enum) | `pdf` / `log` / `synctex` / `aux` / `other`. |
| `content_type` | `text` | MIME type. |
| `size_bytes` | `bigint` | |
| `storage_key` | `text` | key/path in the spec-14 storage backend. |
| `etag` | `text` | content hash (e.g. sha256 hex) for HTTP `ETag`/dedup. |
| `created_at` | `timestamptz` | default now. |

Indexes: `(compile_id)`, `(project_id, created_at)`, unique `(compile_id, name)`.

> The `compiles` row already records `has_pdf` and `artifact_manifest` (spec 22).
> This table is the authoritative per-artifact record with storage keys.

### 5.2 Backend / API

#### 5.2.1 Storage key layout (spec-14 backend)

Deterministic, collision-free, and easy to bulk-delete per compile/project:

```
compiles/{project_id}/{compile_id}/{name}
# examples:
compiles/3f.../9a.../output.pdf
compiles/3f.../9a.../main.log
compiles/3f.../9a.../main.synctex.gz
```

All artifact bytes go through the spec-14 `Storage` interface (never written to
ad-hoc paths). The disk backend roots this under its configured base dir; the S3
backend uses the same key as an object key.

#### 5.2.2 `OutputStore` service (`outputs.py`)

```python
class OutputStore:
    def __init__(self, *, storage: Storage, repo: OutputRepository,
                 settings: Settings, logger) -> None: ...

    async def persist(self, compile_id: UUID, project_id: UUID,
                      result: CompileResult) -> list[CompileOutput]:
        """Copy every artifact in result.artifacts into storage and record rows.
        Idempotent per (compile_id, name): re-persisting overwrites/upserts."""

    async def open_pdf(self, compile_id: UUID) -> StoredObject | None: ...
    async def open_log(self, compile_id: UUID) -> StoredObject | None: ...
    async def list_outputs(self, compile_id: UUID) -> list[CompileOutput]: ...
    async def delete_for_compile(self, compile_id: UUID) -> None: ...
    async def delete_for_project(self, project_id: UUID) -> None: ...
```

- `persist` classifies each artifact into `kind` by name/extension
  (`*.pdf`→pdf, `*.log`→log, `*.synctex.gz`→synctex, `*.aux/.fls/.fdb*`→aux,
  else other), computes an `etag` (sha256), streams the bytes into storage, and
  upserts a `compile_outputs` row. It must respect `COMPILE_MAX_OUTPUT_BYTES`
  (already enforced by spec 21) and skip/flag anything pathological.
- `StoredObject` exposes `size`, `content_type`, `etag`, and an async
  byte-range reader (`async def read_range(start, end) -> AsyncIterator[bytes]`)
  plus a full `stream() -> AsyncIterator[bytes]`, delegating to spec-14.

#### 5.2.3 Wire into spec-22 job

Replace spec-22's output-persistence stub: in `run_compile`, after mapping the
result, call `output_store.persist(compile_id, project_id, result)` **before**
the workdir is cleaned (spec 21 keeps the workdir alive until the service returns;
ensure persistence reads bytes before cleanup — coordinate via the result's
artifact `abs_path`, or have spec 21 defer cleanup until the job signals done).
Persist failures set the compile `status=error` with a clear message but do not
crash the worker.

> Implementation note: to avoid a workdir-lifetime race, the cleanest option is
> for the **job** to own workdir cleanup: spec 21's service is invoked with
> `keep_workdir=True` from the job, the job persists artifacts, then the job
> calls `cleanup_workdir`. Document whichever approach is chosen in the ADR;
> keep it consistent with spec 21's contract.

#### 5.2.4 Endpoints

All require auth + project access (same authz as spec 22). Error envelope per
spec 02.

**`GET /api/v1/projects/{project_id}/compile/{compile_id}/outputs`**
- Returns a list of `OutputSummary` `{ name, kind, content_type, size_bytes,
  etag }`. 404 if the compile is unknown / not in the project.

**`GET /api/v1/projects/{project_id}/compile/{compile_id}/output.pdf`**
- Streams the PDF. Headers: `Content-Type: application/pdf`,
  `Content-Length`, `Accept-Ranges: bytes`, `ETag`, `Cache-Control:
  private, max-age=…`. Content-Disposition `inline` (it is previewed, not
  forced-download) with a sensible filename.
- **Range requests:** honour `Range: bytes=start-end`. Respond **206 Partial
  Content** with `Content-Range` and the requested slice; respond **416** for an
  unsatisfiable range. A full request (no `Range`) returns **200**. This is
  required so PDF.js can do incremental/linearised range loading.
- **Conditional:** support `If-None-Match` → **304** when the ETag matches.
- 404 if no PDF exists for the compile (e.g. it failed).

**`GET /api/v1/projects/{project_id}/compile/{compile_id}/output.log`**
- Streams the LaTeX `.log` as `text/plain; charset=utf-8` with `ETag` and
  `Content-Length`. 404 if absent. (No range requirement.)

**(Optional)** a generic `…/output/{name}` streamer for aux artifacts behind the
same authz, returning the recorded `content_type`. Not a DoD item.

#### 5.2.5 Repository (`output_repository.py`)

`OutputRepository`: `upsert`, `list_for_compile`, `get_by_name`,
`delete_for_compile`, `delete_for_project`, `list_compiles_for_retention(...)`
(returns compile ids beyond the keep-window per project, oldest first).

### 5.3 Frontend / UI

None (spec 24). The typed API client may gain the output endpoints, but no UI.

### 5.4 Real-time / jobs / external integrations

#### Retention/cleanup job

An ARQ job `cleanup_compile_outputs` (scheduled via ARQ cron, e.g. every
`COMPILE_RETENTION_SWEEP_S`):
1. For each project with compiles, find compiles beyond `COMPILE_RETAIN_PER_PROJECT`
   (keep the newest N) **and/or** older than `COMPILE_RETENTION_MAX_AGE_S`.
2. For each such compile: `output_store.delete_for_compile` (storage objects +
   `compile_outputs` rows). Optionally also delete the `compiles` row, or mark it
   `pruned` (keep the metadata row but drop outputs — choose and document; default:
   delete outputs, keep the `compiles` status row for history).
3. Bounded batch size per run to avoid long jobs; log counts.

Also delete outputs when a **project is deleted** (hook into spec 11's project
deletion, or rely on FK cascade for rows + an explicit storage sweep, since
storage objects are not FK-managed — implement `delete_for_project` and call it
on project deletion).

### 5.5 Configuration

#### New env vars (add to `.env.example`)

| Var | Default | Meaning |
| --- | --- | --- |
| `COMPILE_OUTPUT_PREFIX` | `compiles` | Storage key prefix for compile outputs. |
| `COMPILE_RETAIN_PER_PROJECT` | `10` | Keep the newest N compiles' outputs per project. |
| `COMPILE_RETENTION_MAX_AGE_S` | `2592000` (30 d) | Expire outputs older than this. |
| `COMPILE_RETENTION_SWEEP_S` | `3600` | Cleanup-job interval. |
| `COMPILE_RETENTION_BATCH` | `200` | Max compiles processed per sweep. |
| `COMPILE_PDF_CACHE_MAX_AGE_S` | `60` | `Cache-Control: private, max-age` for the PDF response. |

## 6. Overleaf reference (study only — never copy)

> Overleaf's CLSI caches outputs per build id, finds output files by walking the
> compile dir, optimises PDFs, and archives them. Inkstave takes the *key-by-build*
> and *retention* concepts but stores via its own spec-14 abstraction.

- `services/clsi/app/js/OutputCacheManager.js` — keying outputs by a build id,
  the per-project output directory layout, and bulk cleanup of old build dirs.
  Informs Inkstave's `compiles/{project}/{compile}/…` layout and the retention
  job.
- `services/clsi/app/js/OutputController.js` — serving outputs over HTTP (and the
  zip-download path). Informs Inkstave's streaming endpoints and headers (we add
  explicit range support for PDF.js).
- `services/clsi/app/js/OutputFileFinder.js` — discovering which files are
  outputs. Inkstave already has the artifact list from spec 21, so this is just
  the classification idea (pdf/log/synctex/aux).
- `services/clsi/app/js/OutputFileArchiveManager.js` — the optional archive/zip
  approach (only if the optional zip endpoint is implemented). Concept only.

## 7. Acceptance criteria

> Use a fake/disk storage backend in a temp dir and synthetic `CompileResult`s;
> no real compiles.

1. **Given** a `CompileResult` with a PDF, a log, a synctex and an aux file,
   **when** `OutputStore.persist` runs, **then** four `compile_outputs` rows
   exist with correct `kind` classification, the bytes are retrievable from
   storage under `compiles/{project}/{compile}/…`, and each row has a non-empty
   `etag` and correct `size_bytes`/`content_type`.
2. **Given** a successful compile processed by the spec-22 job (with persistence
   wired in), **when** the job finishes, **then** the outputs are persisted
   before the terminal status event and `has_pdf` matches reality.
3. **Given** a persisted PDF, **when** `GET …/output.pdf` is requested with no
   `Range`, **then** it returns **200**, `Content-Type: application/pdf`,
   `Accept-Ranges: bytes`, correct `Content-Length`, and an `ETag`.
4. **Given** a persisted PDF, **when** requested with `Range: bytes=0-99`,
   **then** it returns **206**, `Content-Range: bytes 0-99/<total>`, and exactly
   100 bytes.
5. **Given** a persisted PDF, **when** requested with an unsatisfiable range
   (start ≥ size), **then** it returns **416**.
6. **Given** a matching `If-None-Match` ETag, **when** the PDF is requested,
   **then** it returns **304** with no body.
7. **Given** a persisted log, **when** `GET …/output.log` is requested, **then**
   it returns the log as `text/plain; charset=utf-8` with the correct length.
8. **Given** a compile that produced no PDF (failure), **when**
   `GET …/output.pdf` is requested, **then** it returns **404**.
9. **Given** a user without access to the project, **when** any output endpoint
   is requested, **then** it returns **403/404** (consistent with spec 08) and no
   bytes leak.
10. **Given** a project with more than `COMPILE_RETAIN_PER_PROJECT` compiles,
    **when** `cleanup_compile_outputs` runs, **then** outputs for the oldest
    compiles beyond the window are deleted from both storage and
    `compile_outputs`, the newest N are retained, and the batch is bounded.
11. **Given** outputs older than `COMPILE_RETENTION_MAX_AGE_S`, **when** cleanup
    runs, **then** they are removed regardless of count.
12. **Given** a project is deleted, **when** deletion runs, **then**
    `delete_for_project` removes its storage objects (not just DB rows).

## 8. Test plan

> No real compiles. Synthesize `CompileResult`s with small byte blobs written to
> a temp-dir disk storage backend (and, if feasible, a fake S3 backend) and drive
> the store/endpoints directly.

- **Unit (pytest):**
  - Artifact classification (name/extension → `kind`).
  - ETag computation stability and `size_bytes`/`content_type` correctness.
  - Range math: start/end parsing, 206 slice boundaries, 416 detection, 304 on
    ETag match (test the helper in isolation).
  - Retention selection logic (`list_compiles_for_retention`): keep-newest-N and
    age cutoff, batch bounding.
- **Integration (pytest + httpx + test DB + temp disk storage):**
  - `persist` then list/stream round-trips for PDF, log, aux.
  - Range, 200, 206, 416, 304 HTTP behaviours end-to-end.
  - Authz: 403/404 for non-members.
  - Spec-22 job with persistence wired in (compile service still stubbed):
    assert outputs land in storage and the terminal event fires after persistence.
  - `cleanup_compile_outputs` over a seeded set: storage + rows removed
    correctly; project-delete sweep removes storage objects.
- **E2E (Playwright):** none here (UI is spec 24).
- **Performance/budget note:** all bytes are tiny in-memory blobs on a temp disk
  backend; no subprocess or network. Retention tests seed rows directly.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (`OutputStore`, endpoints, retention
      job, spec-22 wiring, migration).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; no real compiles in any tier.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] Alembic migration for `compile_outputs` added.
- [ ] Range/conditional HTTP semantics verified (200/206/304/416).
- [ ] New env vars documented in `.env.example`; retention job registered.
- [ ] No Overleaf code copied.
