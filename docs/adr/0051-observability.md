# ADR 0051 — Observability: structured logs, request context, metrics, health

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 51 — Observability (Phase 7, first hardening spec)

## Context

Spec 02 gave us a request-id middleware and a JSON-ish logger. Production needs
correlated structured logs, a Prometheus `/metrics` surface, deep readiness probes,
and an optional tracing seam — without paying for any of it in dev/test.

## Decisions

### 1. One correlation context via contextvars

`inkstave.observability.context` holds `request_id`, `trace_id`, `user_id`,
`project_id`, `ws_session_id`, `job_id`, `job_name` as `ContextVar`s with
`bind_context`/`clear_context`/`current_context`. The log formatter reads
`current_context()` and merges the bound (non-None) fields into every line — so no
call site threads ids. The HTTP middleware binds `request_id`/`trace_id`; the auth
dependency binds `user_id` on resolve; the collab WS binds `ws_session_id`; ARQ jobs
bind `job_id`/`job_name` and the **chained** `request_id` of the enqueuing request.

### 2. A custom ~40-line JSON formatter, not a config framework

`JsonLogFormatter` emits one single-line JSON object with the required schema
(`timestamp` ISO-8601 UTC `Z`, `level`, `logger`, `message`, `service`, `env`),
merges the context, adds call-site `http.*`/`error.*` extras, and **redacts** through
a single `redact()` helper. Redaction matches secret **substrings**
(`password`, `authorization`, `secret`, `api_key`/`api-key`, `cookie`) — covering the
spec denylist (incl. `set-cookie`, `x-api-key`, `openrouter_api_key`,
`hashed_password`) while never false-positiving benign keys like `tokens_prompt`.
Logs go to stdout only.

### 3. RequestContextMiddleware (outermost), route-template label

The pure-ASGI middleware honours a valid inbound `X-Request-ID`
(`^[A-Za-z0-9._-]{1,128}$`, else a fresh uuid4), sets `trace_id = active span or
request_id`, echoes `X-Request-ID`, and emits exactly **one** `info` finish log +
`observe_http`. Starlette doesn't persist the matched route on the outer scope, so the
middleware resolves the **route template** by matching the request against the app's
flattened routes (`/api/v1/projects/{project_id}`, never the raw id) — bounding
metric/label cardinality; `/metrics`, `/healthz`, `/readyz` are excluded from logs and
request metrics.

### 4. Prometheus metrics: define-once, reuse-by-name

`metrics.py` registers the spec catalogue once, guarded against duplicate registration
(`_metric` returns the live collector on reload). Counters use base names so
prometheus appends `_total`. Thin helpers (`observe_http`, `observe_compile`,
`inc_agent_tokens` with a model allow-list, `track_job`, `track_ws`, `set_build_info`)
keep call sites clean. Queue depth is sampled **lazily at scrape time** inside the
async `/metrics` endpoint and **fails soft** (a Redis hiccup logs a warning and returns
200). Content type is pinned to `text/plain; version=0.0.4`.

### 5. Tracing is lazy and off by default

`setup_tracing` imports nothing from `opentelemetry` unless `OTEL_ENABLED=true`;
`current_trace_id()` short-circuits to `None` when off, so `trace_id == request_id`.
OpenTelemetry is an optional dependency (not installed in the default image).

### 6. `/healthz` (liveness) + `/readyz` (per-dep timeout) + `/metrics`

`/healthz` never touches deps. `/readyz` checks DB (`SELECT 1`) and Redis (`PING`) each
under `READINESS_CHECK_TIMEOUT_S`, returning 503 with the failing check marked
`error`. (The spec-02 `/health` + `/ready` remain as aliases.)

## Consequences

- New `inkstave.observability` package (context, log, metrics, tracing, middleware) +
  `prometheus-client` dependency. 11 new settings, all in `.env.example`. The old
  `inkstave.logging` now delegates its request-id var to the shared context.
- Integration touch-points: auth (`user_id`), collab WS (`track_ws` + ws context),
  compile job (`track_job` + `observe_compile` + chained request_id), agent job
  (`inc_agent_tokens`/`inc_agent_request`).
- 17 tests: redaction, formatter schema/redaction, context isolation, metric helper
  idempotency + `track_job`/`track_ws` on exception, agent-token helper, request-id
  roundtrip + finish-log schema + route template, `/metrics`, `/healthz`/`/readyz`,
  redis-down scrape, WS gauge round-trip, compile-job metrics + job context.
- Suite ~64s; tracing off, no real LLM/Tectonic/network.

## Log-field schema (spec §5.2.1)

Every structured-log line is one JSON object. The base fields are always present;
context fields appear when bound (`inkstave.observability.context`); call-site extras
appear on the records that carry them (e.g. the request-finish line, error records).
Field/value sources are `observability/log.py`, `context.py`, and `middleware.py`.

| Field | Type | Description |
| --- | --- | --- |
| `timestamp` | string | Event time, ISO-8601 UTC with a `Z` suffix. |
| `level` | string | Lower-cased log level (`info`, `warning`, `error`, …). |
| `logger` | string | Logger name (the `inkstave.*` channel). |
| `message` | string | Rendered log message. |
| `service` | string | Service name (`SERVICE_NAME`). |
| `env` | string | Deployment environment (`ENV_NAME`). |
| `request_id` | string | Correlation id for the HTTP request / chained into jobs (context). |
| `trace_id` | string | Active span id, or the `request_id` when tracing is off (context). |
| `user_id` | string | Authenticated user id, bound by the auth dependency (context). |
| `project_id` | string | Project id, bound where a project is in scope (context). |
| `ws_session_id` | string | Collaboration WebSocket session id (context). |
| `job_id` | string | ARQ job id (context). |
| `job_name` | string | ARQ job name, e.g. `run_compile` (context). |
| `http.method` | string | Request method, on the request-finish line. |
| `http.path` | string | Matched **route template** (bounded cardinality), not the raw path. |
| `http.status_code` | int | Response status code. |
| `http.duration_ms` | float | Request duration in milliseconds. |
| `error.type` | string | Exception class name, on error records. |
| `error.stack` | string | Formatted traceback, only when `LOG_STACKS` is enabled. |

Secret-bearing keys (`password`/`hashed_password`, `authorization`, `secret`,
`api_key`/`api-key`, `access_key`, `cookie`/`set-cookie`) are redacted to
`***REDACTED***` by `redact()` before emission.

## Metric catalogue (spec §5.3)

Registered once in `observability/metrics.py`. Counters use base names; Prometheus
appends `_total` on exposition.

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `inkstave_http_requests_total` | counter | `method`, `path`, `status` | HTTP requests served. |
| `inkstave_http_request_duration_seconds` | histogram | `method`, `path` | HTTP request latency. |
| `inkstave_ws_connections_active` | gauge | `kind` | Active WebSocket connections. |
| `inkstave_ws_messages_total` | counter | `direction`, `kind` | WebSocket messages relayed. |
| `inkstave_compile_duration_seconds` | histogram | `engine`, `status` | LaTeX compile latency. |
| `inkstave_compile_total` | counter | `status` | Compiles by terminal status. |
| `inkstave_agent_tokens_total` | counter | `direction`, `model` | Agent LLM tokens (model allow-listed, else `other`). |
| `inkstave_agent_requests_total` | counter | `status` | Agent runs by status. |
| `inkstave_job_queue_depth` | gauge | `queue` | Pending ARQ jobs (sampled lazily at scrape time). |
| `inkstave_job_duration_seconds` | histogram | `job_name`, `status` | ARQ job duration. |
| `inkstave_build_info` | gauge | `version`, `git_sha` | Build info (always set to `1`). |
| `inkstave_rate_limit_errors_total` | counter | `policy` | Rate-limit backend failures. |

## Operator notes

- Scrape `/metrics` (`scrape_configs: [{job_name: inkstave, static_configs: [{targets:
  ['backend:8000']}], metrics_path: /metrics}]`). Ship stdout JSON to a collector.
- For multi-worker images set `PROMETHEUS_MULTIPROC_DIR` and use multiprocess mode;
  the single-registry default fits the single-process dev/test target.
- Enable tracing with `OTEL_ENABLED=true` + `OTEL_EXPORTER_OTLP_ENDPOINT` to a
  collector; gate `/metrics` to an internal network with `METRICS_PUBLIC` in prod.
