# ADR 0022 — Async compile: ARQ jobs, concurrency, debounce, SSE

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 22 — Compile API & Async ARQ Jobs

## Context

Spec 21 gave a synchronous `CompileService.compile`. Running Tectonic inside a
request would block a worker for seconds; instead a `POST` **enqueues an ARQ job**
that runs the service on a background worker and reports status asynchronously
(poll or SSE). This is Inkstave's first use of ARQ.

## Decisions

### 1. Status/metadata only in a `compiles` table

A new `compiles` table holds **status + metadata** (`queued/running/success/
failure/timeout/cancelled/error`), the ARQ `job_id`, `exit_code`, `duration_ms`,
`has_pdf`, a `log_excerpt`, and an `artifact_manifest` (JSONB). The **bytes** of
the PDF/log are NOT stored here — the job hands the `CompileResult` to a
`persist_hook` (a no-op now; spec 23 plugs in). Indexes: `(project_id,
created_at)`, `job_id`, `status`, `requested_by`.

### 2. Coordinator: debounce + concurrency at enqueue time

`CompileCoordinator` (router-independent, unit-tested) brokers a request:

- **Debounce/coalesce** (`COMPILE_DEBOUNCE_COALESCE`, default on): a non-`force`
  request for a project that already has a `queued`/`running` compile returns
  that in-flight compile (no new row/job). `force=true` bypasses debounce.
- **Concurrency caps**: counts of `queued`+`running` per project
  (`COMPILE_MAX_CONCURRENT_PER_PROJECT`, default 1) and per user
  (`…_PER_USER`, default 3). Exceeding → `429 compile_concurrency_limit` with a
  `Retry-After`; no job enqueued.

### 3. The ARQ job (`run_compile`)

One try only (`max_tries=1`) — a LaTeX failure is a user-facing **result**, not a
job error to retry. The job: load row → early-exit if terminal/cancelled →
`running` + publish → build `CompileOptions` + `CancelToken` + a **cancel
watcher** → `await service.compile(...)` (the seam mocked in all tests) → map
result to row fields → `persist_hook` → terminal status + publish. An unexpected
exception → `error` status (recorded, not retried). The **`COMPILE_JOB_TIMEOUT_S`
must strictly exceed `TECTONIC_COMPILE_TIMEOUT_S`** (settings-validated) so the
engine's own timeout fires first and yields a clean `TIMEOUT` (Overleaf's
"lock > compile" invariant).

### 4. Cancellation over Redis (best-effort cooperative)

The cancel endpoint sets `compile:cancel:{id}` (short TTL) and publishes to the
same channel. The worker checks the flag before starting (aborts a still-queued
compile → `cancelled`) and runs a small watcher that polls the flag and trips
the in-process `CancelToken` passed to spec 21. Cancelling a terminal compile is
idempotent. Single-Redis assumption is documented (no cross-node lock manager).

### 5. Live status: SSE over Redis pub/sub

The job publishes the full `CompileStatusResponse` to `compile:events:{id}` on
every transition. `GET …/events` returns `text/event-stream`: it reads the DB for
the **initial snapshot**, then relays pub/sub transitions, then closes on the
terminal event. To avoid losing a transition, the endpoint **subscribes before
yielding the snapshot**; keep-alives fire only after the real interval elapsed
(so a fakeredis subscribe-ack `None` isn't mistaken for one). SSE auth accepts the
token via the `Authorization` header **or** an `?access_token=` query param
(documented browser trade-off). A WS contract
`{type:"compile_status", payload: CompileStatusResponse}` is defined for spec 29
to relay the same events (transport optional here).

## Consequences

- New dependency `arq`; a worker module (`compile/worker.py`,
  `WorkerSettings`) and an `ArqEnqueuer` (DI dependency, overridden with a fake in
  tests). The enqueuer is built lazily so the test suite never opens a real ARQ
  pool. New settings (`COMPILE_MAX_CONCURRENT_*`, `…_DEBOUNCE_COALESCE`,
  `…_JOB_TIMEOUT_S`, `…_QUEUE_NAME`, `…_SSE_KEEPALIVE_S`, `…_CANCEL_FLAG_TTL_S`).
- Tests run **zero real compiles**: the service is stubbed, ARQ jobs are called
  directly with a hand-built ctx, and fakeredis backs pub/sub. The SSE relay is
  tested at the generator level (in-process httpx streaming deadlocks).
- Spec 23 implements `persist_hook` to store the artifacts; spec 24's preview UI
  calls these endpoints.

## Alternatives considered

- **Synchronous compile over HTTP (Overleaf CLSI model)** — ties up a request
  worker for seconds; rejected for the ARQ job + 202 + status model.
- **Auto-retrying failed compiles** — wrong: a LaTeX failure is a deterministic
  result; `max_tries=1`.
- **WebSocket-only status** — SSE is simpler for one-way status; the WS contract
  is defined for the collab layer to reuse later.
