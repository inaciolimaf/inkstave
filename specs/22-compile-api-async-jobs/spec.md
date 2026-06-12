# Spec 22 — Compile API & Async ARQ Jobs (requirements)

## 1. Summary

This spec exposes compilation to clients **asynchronously**. A `POST` endpoint
enqueues an **ARQ job** that runs the spec-21 `CompileService` on a worker; the
job records status transitions (`queued → running → success | failure | timeout
| cancelled | error`) in a `compiles` table. Clients learn the outcome by
polling a `GET` status endpoint or subscribing to a live stream (SSE, with a WS
fallback contract defined). The spec adds per-user/per-project **concurrency
limits**, **debouncing** of rapid repeat compiles, and **cancellation**. It does
**not** serve the produced PDF bytes — that is spec 23; this spec persists only
status/metadata and the artifact manifest the worker hands off.

## 2. Context & dependencies

- **Depends on:**
  - **Spec 21** — `CompileService.compile(opts, cancel)` synchronous service,
    `CompileResult`, `CompileStatus`, `CancelToken`.
  - **Spec 02** — FastAPI app factory, settings, Redis client, ARQ worker
    bootstrap, structured logging, error envelope.
  - **Spec 04** — testing foundation: fakeredis/ARQ-in-test helpers, httpx async
    client fixtures, the 2-min budget harness.
  - **Spec 11** (project model) — projects exist and are owned by users; used for
    authz and the FK.
  - **Spec 08** (auth guards) — `current_user` dependency for protecting routes.
- **Unlocks:**
  - **Spec 23** — consumes the job's artifact manifest to persist outputs.
  - **Spec 24** — the preview UI calls these endpoints.
- **Affected areas:** backend (`backend/app/compile/api.py`, `jobs.py`,
  `models.py`, `repository.py`, `stream.py`), DB migration, ARQ worker
  registration, `.env.example`, docs.

## 3. Goals

- `POST /api/v1/projects/{project_id}/compile` enqueues a compile and returns a
  `compile_id` immediately (202).
- An ARQ job `run_compile` that loads inputs, invokes spec-21, updates status,
  and hands the artifact manifest to a persistence hook (spec 23 plugs in here).
- `GET /api/v1/projects/{project_id}/compile/{compile_id}` returns current
  status + metadata.
- A live stream: `GET …/compile/{compile_id}/events` (SSE) emitting status
  transitions; define an equivalent WS message contract for reuse by the collab
  layer.
- **Concurrency limits** per project and per user, enforced at enqueue time.
- **Debouncing**: a new compile request for a project that already has a
  queued/running compile either returns the in-flight one or supersedes it
  (configurable; default = coalesce to in-flight).
- **Cancellation**: `DELETE …/compile/{compile_id}` (or `POST …/cancel`) signals
  the job's `CancelToken` and marks the compile cancelled.
- Clean, typed **job signature and result shape**.

## 4. Non-goals (explicitly out of scope)

- Serving PDF/log/synctex bytes, range requests, retention/cleanup — spec 23.
- PDF preview UI, log panel UI — spec 24.
- SyncTeX resolution — spec 26; log parsing — spec 27.
- Cross-node distributed locking semantics beyond a Redis-key lock (single Redis
  is assumed; document the assumption).
- Compile output caching / content-addressing.

## 5. Detailed requirements

### 5.1 Data model

New table **`compiles`** (Alembic migration required):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | `UUID` PK | the `compile_id`. |
| `project_id` | `UUID` FK → `projects.id` | `ON DELETE CASCADE`, indexed. |
| `requested_by` | `UUID` FK → `users.id` | who triggered it, indexed. |
| `status` | `text` (enum) | `queued`/`running`/`success`/`failure`/`timeout`/`cancelled`/`error`. |
| `main_file` | `text` | root document path used. |
| `job_id` | `text` | ARQ job id, nullable, indexed (for cancel lookup). |
| `error_message` | `text` | nullable; system/validation error summary. |
| `exit_code` | `integer` | nullable. |
| `duration_ms` | `integer` | nullable; engine wall-clock. |
| `artifact_manifest` | `jsonb` | nullable; list of `{name, rel_path, size_bytes, content_type}` from `CompileResult.artifacts` (spec 23 reads this). |
| `has_pdf` | `boolean` | default `false`; true when a PDF artifact exists. |
| `log_excerpt` | `text` | nullable; truncated tail of `log_text` for quick display (full log persisted by spec 23). |
| `created_at` | `timestamptz` | default now, indexed. |
| `started_at` | `timestamptz` | nullable. |
| `finished_at` | `timestamptz` | nullable. |

Indexes: `(project_id, created_at desc)` for listing the latest compile;
`job_id`; `status`. Use a DB-level enum or a checked `text` column consistent
with how spec 03 modelled enums.

> Note: this table stores **status/metadata only**. The actual bytes of the PDF
> and full log are stored by spec 23, keyed by `compile_id`.

### 5.2 Backend / API

All endpoints require auth (`current_user`) and authorize that the user may
access `project_id` (owner, or — once collaboration lands — an editor/viewer per
spec 34; for now: project owner). Use the standard error envelope from spec 02.

#### 5.2.1 `POST /api/v1/projects/{project_id}/compile`

- **Auth:** required; user must have compile rights on the project.
- **Request body** (Pydantic `CompileRequest`):
  ```json
  { "main_file": "main.tex", "force": false }
  ```
  - `main_file` optional; defaults to the project's configured root document or
    `main.tex`.
  - `force` optional (default `false`): when `true`, bypass debounce/coalescing
    and always create a new compile (still subject to concurrency caps).
- **Behaviour:**
  1. Authorize.
  2. **Debounce/coalesce:** if `force` is false and a `queued` or `running`
     compile exists for this project, return that compile (202 with its id)
     instead of creating a new one.
  3. **Concurrency caps:** if creating a new compile would exceed
     `COMPILE_MAX_CONCURRENT_PER_PROJECT` or `COMPILE_MAX_CONCURRENT_PER_USER`
     (count of `queued`+`running`), respond **429** with a `Retry-After` hint and
     a machine-readable error code `compile_concurrency_limit`.
  4. Insert a `compiles` row with `status=queued`.
  5. Enqueue ARQ job `run_compile(compile_id)`; store the returned `job_id`.
  6. Respond **202** with `CompileStatusResponse` (see below).
- **Response 202** (`CompileStatusResponse`):
  ```json
  {
    "id": "…", "project_id": "…", "status": "queued",
    "main_file": "main.tex", "has_pdf": false,
    "created_at": "…", "started_at": null, "finished_at": null,
    "duration_ms": null, "exit_code": null, "error_message": null
  }
  ```
- **Errors:** 401 (unauth), 403 (no access), 404 (project not found), 422
  (invalid body), 429 (concurrency).

#### 5.2.2 `GET /api/v1/projects/{project_id}/compile/{compile_id}`

- Returns the `CompileStatusResponse` for that compile. 404 if not found or not
  in this project. Includes `log_excerpt` and `artifact_manifest` summary so a
  client can decide whether to fetch outputs (spec 23).

#### 5.2.3 `GET /api/v1/projects/{project_id}/compile/latest`

- Convenience: returns the most recent compile for the project (by
  `created_at`), or 404 if none.

#### 5.2.4 `GET /api/v1/projects/{project_id}/compile/{compile_id}/events` (SSE)

- **Auth:** required (token via header; for browsers that cannot set SSE headers,
  accept the access token as a query param `?access_token=` — document the
  trade-off, prefer cookie/header where possible).
- Emits Server-Sent Events. Each event is `event: status` with JSON data equal
  to `CompileStatusResponse`. The server sends:
  - an immediate snapshot of the current status,
  - one event per transition (`queued→running`, terminal state),
  - periodic `: keep-alive` comments,
  - a final event then closes the stream once a terminal state is reached.
- Implemented by subscribing to a Redis pub/sub channel
  `compile:events:{compile_id}` that the job publishes to; the endpoint also
  reads the DB for the initial snapshot to avoid missing early transitions.
- **WS contract (defined, reuse by collab layer):** an equivalent message shape
  `{ "type": "compile_status", "payload": CompileStatusResponse }` so spec 29's
  WebSocket can relay the same events. Implementing the WS transport is optional
  here; the SSE endpoint is the required deliverable.

#### 5.2.5 `POST /api/v1/projects/{project_id}/compile/{compile_id}/cancel`

- Marks intent to cancel. If the compile is `queued`, abort it (`status=cancelled`,
  do not run). If `running`, signal cancellation (see §5.4) so the worker stops
  the Tectonic process via spec-21's `CancelToken`; the job sets
  `status=cancelled`. Idempotent: cancelling an already-terminal compile returns
  the current status (200) without error. Responds with `CompileStatusResponse`.

#### 5.2.6 Repository / service layer

- `CompileRepository` (async SQLAlchemy): `create`, `get`, `get_latest`,
  `count_active_for_project`, `count_active_for_user`, `find_active_for_project`,
  `set_status(...)`, `set_result(...)`.
- `CompileCoordinator` encapsulates debounce + concurrency + enqueue logic so the
  router stays thin and the logic is unit-testable without HTTP.

### 5.3 Frontend / UI

None in this spec (the API client wiring and preview UI are spec 24). Optionally
extend the typed API client from spec 09 with the compile endpoints, but no
visible UI.

### 5.4 Real-time / jobs / external integrations

#### 5.4.1 ARQ job signature & result shape

Registered in the ARQ worker settings (spec 02). Signature:

```python
async def run_compile(ctx: dict, compile_id: str) -> dict:
    """ARQ task: run one compile to completion.

    ctx provides: db session factory, redis, the DI-built CompileService
    (spec 21), settings, logger. Returns a small JSON-serialisable summary
    (also persisted to the compiles row); the heavy artifacts are handed to the
    output-persistence hook (spec 23), NOT returned through ARQ.
    """
```

Job algorithm:
1. Load the `compiles` row; if it is already terminal or `cancelled`, exit early
   (handles a cancel that arrived before the worker picked it up).
2. Set `status=running`, `started_at=now`; publish a status event.
3. Build `CompileOptions` (project_id, main_file, timeout, compile_id) and a
   `CancelToken`. **Register the token** under a Redis key / in-process registry
   keyed by `compile_id` so the cancel endpoint can trip it (see §5.4.2).
4. `await compile_service.compile(opts, cancel)` — **this is the spec-21 call and
   is the seam mocked in tests**.
5. Map `CompileResult` → row fields: `status`, `exit_code`, `duration_ms`,
   `has_pdf`, `artifact_manifest`, `log_excerpt`, `error_message`.
6. Call the **output-persistence hook** (a no-op stub in this spec; spec 23
   implements it) with `(compile_id, CompileResult)` so the bytes get stored.
7. Set `finished_at=now`, persist, publish the terminal status event.
8. On unexpected exception: set `status=error`, record `error_message`, publish,
   and re-raise only if needed for ARQ retry policy (default: do **not** retry
   compiles automatically — a compile failure is a user-facing result, not a job
   error; configure `max_tries=1` for this task).

**Result shape** returned by the job (and mirrored by the row):
```json
{
  "compile_id": "…", "status": "success", "exit_code": 0,
  "duration_ms": 1234, "has_pdf": true, "artifact_count": 3
}
```

#### 5.4.2 Cancellation transport

Because the cancel request may hit a different process than the worker, signal
via Redis: the cancel endpoint sets `compile:cancel:{compile_id}=1` (short TTL)
and publishes to `compile:cancel:{compile_id}` channel. The worker (a) checks the
flag before starting and (b) runs a small concurrent watcher task that, on the
pub/sub message or flag, trips the in-process `CancelToken` passed to spec 21.
Document this as best-effort cooperative cancellation.

#### 5.4.3 Status pub/sub

The job publishes `CompileStatusResponse` JSON to `compile:events:{compile_id}`
on every transition. The SSE endpoint subscribes. Both use the spec-02 Redis
client.

### 5.5 Configuration

#### New env vars (add to `.env.example`)

| Var | Default | Meaning |
| --- | --- | --- |
| `COMPILE_MAX_CONCURRENT_PER_PROJECT` | `1` | Max simultaneous queued+running compiles per project. |
| `COMPILE_MAX_CONCURRENT_PER_USER` | `3` | Max simultaneous queued+running compiles per user. |
| `COMPILE_DEBOUNCE_COALESCE` | `true` | If true, a non-`force` request returns the in-flight compile instead of creating a new one. |
| `COMPILE_JOB_TIMEOUT_S` | `120` | ARQ job-level hard timeout (must exceed the spec-21 engine timeout + overhead). |
| `COMPILE_QUEUE_NAME` | `compiles` | ARQ queue / Redis key prefix for compile jobs. |
| `COMPILE_SSE_KEEPALIVE_S` | `15` | SSE keep-alive comment interval. |
| `COMPILE_CANCEL_FLAG_TTL_S` | `300` | TTL for the Redis cancel flag. |

The ARQ job-level timeout must be **strictly greater** than spec-21's
`TECTONIC_COMPILE_TIMEOUT_S` so the engine's own timeout fires first and produces
a clean `TIMEOUT` result rather than the job being killed mid-flight (mirrors
Overleaf's "lock timeout > compile timeout" relationship).

## 6. Overleaf reference (study only — never copy)

> Overleaf compiles **synchronously over HTTP** in CLSI and tracks
> per-project locks and persistence in memory; the web service brokers via
> `ClsiManager`. Inkstave instead enqueues an **ARQ job** and reports status
> asynchronously. Take the concepts (one compile at a time per project, debounce,
> request shape), not the synchronous control flow.

- `services/clsi/app/js/CompileController.js` — the HTTP entry point: request
  parsing, marking a project as recently accessed, returning compile outcome and
  output file list. Inkstave's `POST /compile` mirrors the *request* shape but
  returns 202 + a status id instead of the finished result.
- `services/web/app/src/Features/Compile/CompileManager.mjs` and
  `ClsiManager.mjs` — how the web tier brokers a compile, rate-limits, and
  associates outputs with a build id. Inkstave's `CompileCoordinator` covers the
  brokering/limit role; the "build id" maps to Inkstave's `compile_id`.
- `services/clsi/app/js/LockManager.js` — per-project compile lock + global
  concurrency cap, and the lock-timeout > compile-timeout invariant. Inkstave
  enforces concurrency at enqueue time and via the per-project active count,
  using the same invariant for job vs. engine timeouts.

## 7. Acceptance criteria

> The spec-21 `CompileService.compile` is stubbed in all of the following.

1. **Given** an authenticated owner and a valid project, **when** they
   `POST …/compile`, **then** they receive **202** with a new `compile_id`, a row
   exists with `status=queued`, and an ARQ job was enqueued (assert via the test
   ARQ/redis seam).
2. **Given** the worker runs `run_compile` with a service stub returning
   `SUCCESS` + a PDF artifact, **when** it completes, **then** the row is
   `status=success`, `has_pdf=true`, `duration_ms` set, and the artifact manifest
   is recorded.
3. **Given** the service stub returns `FAILURE`, **when** the job completes,
   **then** the row is `status=failure`, `has_pdf=false`, and a `log_excerpt` is
   stored.
4. **Given** the service stub raises an unexpected exception, **when** the job
   runs, **then** the row is `status=error` with an `error_message` and the job
   does not auto-retry (`max_tries=1`).
5. **Given** a project already has a `queued`/`running` compile and
   `COMPILE_DEBOUNCE_COALESCE=true`, **when** a non-`force` `POST …/compile`
   arrives, **then** the existing compile is returned (no new row) ; **and** with
   `force=true` a new row is created (subject to caps).
6. **Given** the per-project active count is at `COMPILE_MAX_CONCURRENT_PER_PROJECT`
   and `force=true`, **when** a new `POST …/compile` arrives, **then** the API
   responds **429** with code `compile_concurrency_limit` and a `Retry-After`
   header, and no job is enqueued.
7. **Given** a `queued` compile, **when** the owner cancels it, **then** its
   status becomes `cancelled` and the worker, if it later picks it up, exits
   early without calling the compile service.
8. **Given** a `running` compile, **when** cancel is requested, **then** the
   cancel flag/pub-sub trips the `CancelToken` passed to the service (assert the
   token was cancelled via the service stub) and the row ends `cancelled`.
9. **Given** a compile transitions queued→running→success, **when** a client is
   connected to the SSE `…/events` endpoint, **then** it receives an initial
   snapshot and a `status` event for each transition, and the stream closes after
   the terminal event.
10. **Given** a `GET …/compile/{id}` for another user's project, **when** called,
    **then** it responds **403** (or **404** to avoid existence leakage — pick one
    consistent with spec 08 and assert it).
11. **Given** no compiles exist, **when** `GET …/compile/latest` is called,
    **then** it responds **404**; after one compile, it returns that compile.
12. **Given** the ARQ job timeout is configured, **then** it is strictly greater
    than spec-21's engine timeout (assert via settings validation).

## 8. Test plan

> No real Tectonic compiles. The spec-21 `CompileService` is injected and
> replaced with stubs/fakes; ARQ runs in-process against fakeredis (or ARQ's test
> helper) so jobs execute synchronously and deterministically.

- **Unit (pytest):**
  - `CompileCoordinator`: debounce/coalesce logic, concurrency-cap decisions,
    `force` handling — pure, no HTTP.
  - `CompileRepository`: CRUD, active counts, latest lookup against the test DB.
  - Status-mapping from a stubbed `CompileResult` to row fields.
  - Cancel-flag/token wiring: a fake service that records whether its
    `CancelToken` was tripped.
- **Integration (pytest + httpx + test DB + fakeredis):**
  - Full HTTP round-trips for `POST`, `GET`, `GET latest`, `cancel`, including
    202/403/404/422/429 paths.
  - Job execution via the ARQ test seam with a `SUCCESS`/`FAILURE`/`error`
    service stub; assert row transitions and that the output-persistence hook was
    invoked with the result.
  - SSE endpoint: connect, drive the job through a transition by publishing to
    the pub/sub channel (or running the stubbed job), assert the events received
    and that the stream terminates.
- **E2E (Playwright):** none required here (UI is spec 24). If a thin smoke is
  added, it must use a **mocked/stubbed compile** (no real Tectonic) so it stays
  in the fast budget.
- **Performance/budget note:** all jobs run with a stubbed service and fakeredis;
  no subprocess, no network. SSE tests use short keep-alive intervals and
  assert-then-close to avoid hanging.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (API, ARQ job, model, migration,
      coordinator, SSE, cancellation).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; no real compiles in any tier.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] Alembic migration for `compiles` added (not editing a released migration).
- [ ] New env vars documented in `.env.example`; ARQ job registered in worker
      settings.
- [ ] No Overleaf code copied.
