# Spec 51 — Observability (requirements)

## 1. Summary

This spec turns Inkstave's basic logging (spec 02) into production-grade
observability. It delivers: (a) **structured JSON logging** with a request/trace
ID that is generated or accepted at the edge and propagated through HTTP
handlers, WebSocket sessions and ARQ jobs; (b) a Prometheus-style **`/metrics`**
endpoint exposing request latency, compile durations, agent token usage, live
WebSocket connections and job-queue depth; (c) **optional OpenTelemetry tracing**
gated behind a flag and off by default; and (d) **deepened health/readiness**
probes that check the real dependencies. It is the first hardening spec and the
foundation operators rely on to run Inkstave.

## 2. Context & dependencies

- **Depends on:** spec **02** (the FastAPI app factory, Pydantic `Settings`, a
  logging setup, the global exception handlers, and `/healthz` / `/readyz` or
  equivalent stubs). This spec replaces/extends those rather than duplicating
  them.
- **Also instruments (must already exist):** the compile job + API (22), output
  storage (23), the collab WebSocket and rooms (29/34), the agent LLM client and
  streaming/orchestration (41/44), and agent safety/cost accounting (49).
- **Unlocks:** spec **52** (security uses the same middleware chain and request
  context), spec **53** (perf gate reads `/metrics` and structured logs), spec
  **54** (e2e asserts trace IDs surface), spec **56/57** (Docker/CI wire the
  probes and scrape `/metrics`).
- **Affected areas:** backend (logging, middleware, metrics, tracing, health),
  infra (`.env.example`, compose scrape config note), docs (observability ADR +
  field/metric reference).

## 3. Goals

- A single structured-logging module emitting **one JSON object per log line**
  with a stable, documented field schema (§5.2.1).
- A **request-context** mechanism (Python `contextvars`) holding `request_id`,
  `trace_id`, `user_id`, `project_id` so any log call anywhere in the request /
  job lifecycle automatically includes them — no manual threading of IDs.
- HTTP middleware that generates a request ID (or honours an inbound
  `X-Request-ID`), binds the context, logs request start/finish, and returns
  `X-Request-ID` on the response.
- WebSocket and ARQ instrumentation that establish the same context at connection
  / job start.
- A `GET /metrics` endpoint in Prometheus text exposition format with the metric
  names, types, labels and buckets in §5.3.
- Optional OpenTelemetry tracing, enabled only when `OTEL_ENABLED=true`, with a
  no-op default so tests and dev pay nothing.
- `GET /healthz` (liveness, no deps) and `GET /readyz` (readiness, checks
  Postgres + Redis) with the contracts in §5.5.
- Negligible test overhead: structured logging defaults to a quiet level in
  tests, `/metrics` is cheap to assert, tracing is off.

## 4. Non-goals (explicitly out of scope)

- Rate limiting, secure headers, CORS allow-list, input-validation hardening —
  all spec **52** (this spec only establishes the middleware chain those plug
  into).
- The CI gate that fails when the suite exceeds 2 minutes, slow-test detection,
  N+1 audits — spec **53**.
- Shipping logs/metrics/traces to a specific vendor (Grafana/Loki/Tempo/Datadog).
  We expose standard interfaces (stdout JSON, `/metrics`, OTLP) and stop there;
  wiring an exporter is an operator concern documented in §5.5, not code here.
- Alerting rules, dashboards, log retention policies.
- Per-endpoint custom business metrics beyond those listed in §5.3 (more can be
  added later without a spec).

## 5. Detailed requirements

### 5.1 Library choices

- **Metrics:** the official `prometheus-client` Python library (multiprocess
  mode is **not** required for the single-process Uvicorn dev/test target; if the
  production image runs multiple workers, document the
  `PROMETHEUS_MULTIPROC_DIR` approach in the ADR but keep single-registry as the
  default). Do **not** hand-roll a text-format serializer.
- **Logging:** standard-library `logging` configured to emit JSON. Use a small,
  dependency-light JSON formatter (`python-json-logger` is acceptable, or a
  ~30-line custom `logging.Formatter`). Choose one and document it. Logs go to
  **stdout** only (12-factor); no file handlers.
- **Tracing:** `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi` +
  OTLP exporter, all imported lazily so they are not loaded when
  `OTEL_ENABLED=false`.

### 5.2 Structured logging

#### 5.2.1 Log line schema

Every emitted log line is a single-line JSON object. **Required** fields on every
line:

| Field | Type | Source / meaning |
| --- | --- | --- |
| `timestamp` | string (RFC 3339 / ISO-8601, UTC, `Z`) | event time |
| `level` | string | `debug` \| `info` \| `warning` \| `error` \| `critical` |
| `logger` | string | logger name (module path) |
| `message` | string | human-readable message |
| `service` | string | constant `inkstave-backend` (from settings) |
| `env` | string | `development` \| `test` \| `production` |

**Contextual** fields, present when a context is bound (omitted when absent — do
not emit `null` spam):

| Field | Type | Meaning |
| --- | --- | --- |
| `request_id` | string (UUIDv4 or inbound value, ≤128 chars, sanitized) | per-request/job correlation id |
| `trace_id` | string | OTel trace id (hex) when tracing on; otherwise equals `request_id` so logs always correlate |
| `user_id` | string (UUID) | authenticated user, when known |
| `project_id` | string (UUID) | project in scope, when known |
| `ws_session_id` | string | set inside a WS connection |
| `job_id` | string | ARQ job id, set inside a job |
| `job_name` | string | ARQ function name, inside a job |

**Event-specific** fields (added by the call site or the HTTP middleware):

| Field | Type | Where |
| --- | --- | --- |
| `http.method` | string | request-finished log |
| `http.path` | string | the **route template** (e.g. `/api/v1/projects/{id}`), never the raw path with ids, to keep cardinality bounded |
| `http.status_code` | int | request-finished log |
| `http.duration_ms` | float | request-finished log |
| `error.type` | string | exception class, on error logs |
| `error.stack` | string | traceback, on error logs (omit in `production` if `LOG_STACKS=false`) |

**Redaction:** the formatter MUST never emit `authorization`, `cookie`,
`password`, `hashed_password`, `set-cookie`, `x-api-key`, `openrouter_api_key`,
or any field whose key matches a denylist (case-insensitive). Provide a single
`redact(mapping)` helper and a test for it.

#### 5.2.2 Request context

Implement `app/observability/context.py` exposing:

```python
request_id_var: ContextVar[str | None]
trace_id_var: ContextVar[str | None]
user_id_var: ContextVar[str | None]
project_id_var: ContextVar[str | None]
# plus ws_session_id_var, job_id_var, job_name_var

def bind_context(**fields) -> Token: ...   # set provided vars, return reset token(s)
def clear_context(token) -> None: ...
def current_context() -> dict[str, str]: ...  # the non-None vars, for the formatter
```

A `logging.Filter` (or the formatter itself) reads `current_context()` and merges
it into each record. This guarantees correlation IDs without callers passing them.

#### 5.2.3 HTTP middleware (`RequestContextMiddleware`)

Order: it must run **outermost** (before auth, before the spec-52 security
middleware) so even rejected requests are logged with an id. Contract:

1. Read inbound `X-Request-ID`; if present and matching `^[A-Za-z0-9._-]{1,128}$`
   use it, else generate a `uuid4` hex.
2. If tracing is on, read the active span's trace id; else `trace_id = request_id`.
3. `bind_context(request_id=..., trace_id=...)`. Downstream auth dependency, when
   it resolves a user, calls `bind_context(user_id=...)`; project routers bind
   `project_id`.
4. On response, set header `X-Request-ID: <request_id>`.
5. Emit exactly **one** structured `info` log at request finish with the
   `http.*` fields and `http.duration_ms` (start-of-request logging is `debug`
   only, to keep volume down). On unhandled exception, emit one `error` log
   (with `error.type`/`error.stack`) and re-raise to the global handler from
   spec 02 — do not swallow.
6. Always `clear_context` in a `finally`.

`http.path` must be the **matched route template**
(`request.scope["route"].path` after routing, or resolved via the router); if no
route matched (404), use a constant `"<unmatched>"` — never the raw URL.

### 5.3 Metrics

`GET /metrics` returns `text/plain; version=0.0.4` from the prometheus-client
registry. **Auth:** unauthenticated but bindable to an internal network in prod;
expose a setting `METRICS_PUBLIC` (default `true` in dev/test, document gating in
prod). The endpoint is excluded from request-latency metrics and from access
logs to avoid scrape noise.

Metric catalogue (names are stable contracts):

| Name | Type | Labels | Notes |
| --- | --- | --- | --- |
| `inkstave_http_requests_total` | Counter | `method`, `path` (route template), `status` | one inc per finished request; `/metrics` and `/healthz`/`/readyz` excluded |
| `inkstave_http_request_duration_seconds` | Histogram | `method`, `path` | buckets `[.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10]` |
| `inkstave_ws_connections_active` | Gauge | `kind` (`collab`) | inc on WS accept, dec on close (in `finally`) |
| `inkstave_ws_messages_total` | Counter | `direction` (`in`/`out`), `kind` | optional but recommended; low cardinality |
| `inkstave_compile_duration_seconds` | Histogram | `engine` (`tectonic`), `status` (`success`/`failure`/`timeout`) | observed in the compile job, not the API |
| `inkstave_compile_total` | Counter | `status` | per finished compile job |
| `inkstave_agent_tokens_total` | Counter | `direction` (`prompt`/`completion`), `model` | incremented from the agent's token accounting (spec 49); model label normalized/whitelisted to bound cardinality |
| `inkstave_agent_requests_total` | Counter | `status` (`success`/`error`/`rate_limited`) | per agent run |
| `inkstave_job_queue_depth` | Gauge | `queue` | sampled from Redis/ARQ (see §5.4) |
| `inkstave_job_duration_seconds` | Histogram | `job_name`, `status` | observed around each ARQ job |
| `inkstave_build_info` | Gauge (const 1) | `version`, `git_sha` | set once at startup |

Implement a tiny `metrics.py` that defines these once (module-level singletons,
guarded against double-registration so test reloads don't explode). Provide thin
helpers (`observe_http(...)`, `observe_compile(...)`, `inc_agent_tokens(...)`,
context managers `track_job(name)` and `track_ws(kind)`) so call sites stay
clean. **Cardinality rule:** never use a user id, project id, file path, full URL
or raw model string as a label value.

### 5.4 Real-time / jobs / external integrations

- **WebSocket (collab):** at accept, generate `ws_session_id` (uuid4), bind it
  plus `user_id`/`project_id`, `inc` the `ws_connections_active` gauge; on close
  `dec` it and clear context — both in a `finally` so crashes don't leak the
  gauge. Per-message logging stays at `debug`.
- **ARQ jobs:** wrap the worker so each job, on start, binds
  `job_id`/`job_name` and a fresh `request_id` (or one passed in the job kwargs
  to chain from the request that enqueued it — prefer chaining: the enqueuing
  request passes its `request_id` into the job payload). Use `track_job(name)` to
  record `inkstave_job_duration_seconds` and `inkstave_compile_*` where relevant.
  Clear context in `finally`.
- **Queue depth:** sample `inkstave_job_queue_depth` either via a small periodic
  task or **lazily at scrape time** (preferred: a Prometheus `Gauge` with a
  registered callback that reads the ARQ/Redis queue length, e.g.
  `LLEN arq:queue` or the ARQ API). Reading Redis at scrape time must be fast and
  must fail soft (on Redis error, leave the previous value / 0, log a warning,
  never 500 the `/metrics` endpoint).
- **Agent token usage:** spec 49 already accounts tokens; here, after each LLM
  response, call `inc_agent_tokens(direction, model, n)`. Do not call the LLM in
  tests — assert the helper increments the counter with a fake usage object.
- **OpenTelemetry:** when `OTEL_ENABLED=true`, initialize a `TracerProvider` with
  an OTLP exporter to `OTEL_EXPORTER_OTLP_ENDPOINT`, instrument FastAPI (server
  spans) and optionally SQLAlchemy/redis/httpx, and set `trace_id` in the
  context from the active span. When `false` (the default, and always in tests),
  install nothing and skip all imports.

### 5.5 Health & readiness

- **`GET /healthz`** — liveness. No dependency checks. Returns `200`
  `{"status":"ok"}` as long as the process is up. Never touches the DB/Redis.
  Excluded from metrics/access logs.
- **`GET /readyz`** — readiness. Checks: (1) DB — `SELECT 1` on a short-timeout
  connection; (2) Redis — `PING` with a short timeout. Returns `200`
  `{"status":"ready","checks":{"db":"ok","redis":"ok"}}` when all pass; `503`
  with the same shape and the failing check(s) set to `"error"` (plus a logged
  warning) when any fails. Each check has its own timeout (default 2s) so a hung
  dependency can't hang the probe.
- **`GET /metrics`** — §5.3.

### 5.6 Configuration

Add to `.env.example`:

| Var | Default | Purpose |
| --- | --- | --- |
| `LOG_LEVEL` | `info` (`warning` in test) | minimum level emitted |
| `LOG_FORMAT` | `json` | `json` or `console` (pretty, dev only) |
| `LOG_STACKS` | `true` (`false` recommended in prod) | include tracebacks in error logs |
| `SERVICE_NAME` | `inkstave-backend` | `service` log field / build_info |
| `APP_VERSION` | `0.0.0` | `inkstave_build_info` version |
| `GIT_SHA` | `unknown` | `inkstave_build_info` git_sha (set in CI) |
| `METRICS_PUBLIC` | `true` | gate `/metrics` exposure |
| `OTEL_ENABLED` | `false` | turn tracing on |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP target when enabled |
| `OTEL_SERVICE_NAME` | `inkstave-backend` | resource attribute |
| `READINESS_CHECK_TIMEOUT_S` | `2` | per-dependency probe timeout |

Surface all through the Pydantic `Settings`. In the test profile, force
`LOG_LEVEL=warning`, `LOG_FORMAT=json`, `OTEL_ENABLED=false`,
`METRICS_PUBLIC=true`.

Document (ADR/README, not code) the operator wiring: scrape `/metrics`, ship
stdout JSON to a collector, point OTLP at a collector. Provide a one-line
Prometheus scrape-config snippet in docs.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently. These are Node/Express; Inkstave is Python/FastAPI, so
> only the *concepts* transfer.

- `libraries/logger/logging-manager.js` — how they centralize logger config,
  pick level by environment (prod=info, test=fatal/quiet), and attach
  serializers for `err`/`req`/`res`. Learn: environment-driven level, quiet in
  tests, structured serialization — then write your own JSON formatter.
- `libraries/logger/serializers.js` — what they include/redact for request and
  error objects. Learn the *shape* of a safe request/error serialization.
- `libraries/metrics/index.js` — the `/metrics` route injection and the
  `inc`/`timing`/`summary` helpers wrapping `prom-client`. Learn: one registry,
  thin helper API, route returns the registry's text format.
- `libraries/metrics/prom_wrapper.js` — how they lazily create/cache metric
  objects by name and key labels. Learn the "define-once, reuse-by-name" pattern.
- `libraries/metrics/http.js` — per-request timing middleware using the **route
  path** (not raw URL) as the label to bound cardinality. Mirror this idea in the
  FastAPI middleware.

## 7. Acceptance criteria

1. **Given** any HTTP request, **when** it completes, **then** the response
   carries an `X-Request-ID` header and exactly one JSON `info` log line is
   emitted containing `request_id`, `http.method`, `http.path` (route template),
   `http.status_code` and `http.duration_ms`.
2. **Given** a request with an inbound `X-Request-ID: abc-123`, **then** that
   value is used as `request_id` in logs and echoed in the response header; a
   malformed/oversized inbound id is ignored and a fresh uuid is generated.
3. **Given** a log line emitted anywhere inside a request after auth resolved,
   **then** it includes the same `request_id` and the `user_id` without the call
   site passing them explicitly.
4. **Given** a payload containing `password`/`authorization`/`openrouter_api_key`
   keys, **when** it is logged via the helper, **then** those values are redacted
   and never appear in output.
5. **Given** `GET /metrics`, **then** it returns `200` with
   `text/plain; version=0.0.4` and includes the metric names in §5.3, and a
   finished request has incremented `inkstave_http_requests_total` and observed
   `inkstave_http_request_duration_seconds`.
6. **Given** a WebSocket connect then disconnect, **then**
   `inkstave_ws_connections_active{kind="collab"}` rises by 1 then returns to its
   prior value (verified even if the handler raised).
7. **Given** an ARQ compile job, **then** `inkstave_compile_duration_seconds` and
   `inkstave_compile_total{status=...}` are recorded, and the job's logs carry
   `job_id`/`job_name` and the chained `request_id` of the enqueuing request.
8. **Given** the agent emits a usage object, **then**
   `inkstave_agent_tokens_total{direction="prompt"|"completion",model=...}`
   increases accordingly (no real LLM call in the test).
9. **Given** Postgres and Redis are up, **then** `GET /readyz` returns `200` with
   both checks `ok`; **given** Redis is unreachable, **then** `/readyz` returns
   `503` with `redis":"error"` while `/healthz` still returns `200`.
10. **Given** `OTEL_ENABLED=false` (default), **then** no OpenTelemetry modules
    are imported/initialized and `trace_id == request_id` in logs.
11. **Given** the metrics registry, **then** importing the metrics module twice
    (e.g. test reload) does not raise a duplicate-registration error.
12. **Given** Redis is down at scrape time, **then** `/metrics` still returns
    `200` (queue-depth gauge fails soft) and logs a warning.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Tracing is off, logging is at `warning`, and no real LLM/Tectonic/network runs.

- **Unit (pytest):**
  - `redact()` removes every denylisted key (case-insensitive, nested).
  - JSON formatter produces valid single-line JSON with required fields and
    merges `current_context()`; omits unbound contextual fields.
  - `bind_context`/`clear_context` set and reset the contextvars; no leakage
    across two sequential "requests" in the same task.
  - Metric helpers register once and are idempotent on re-import (guarded
    registry); `track_job`/`track_ws` increment/decrement correctly, including on
    exception (use `pytest.raises`).
  - Route-template extraction returns the template, and `<unmatched>` for 404s.
- **Integration (pytest + httpx + test DB + fakeredis or test Redis):**
  - A request through the real app: `X-Request-ID` round-trips; capture logs (via
    `caplog`/a buffer stream) and assert one finish log with the schema; assert
    counters/histogram moved by querying the registry
    (`prometheus_client.generate_latest` or `REGISTRY.get_sample_value`).
  - `/metrics` returns the expected content type and metric names.
  - `/healthz` always 200; `/readyz` 200 when deps up, 503 when Redis ping is
    monkeypatched to fail (and `/healthz` unaffected).
  - WS connect/disconnect moves the gauge (use the test WS client from spec 29);
    assert the gauge returns to baseline even when the handler raises.
  - An ARQ job run via the test worker harness binds job context and records the
    duration histogram; agent token helper increments the counter with a faked
    usage object.
- **E2E (Playwright):** none here; spec 54 asserts an `X-Request-ID` is present
  on an API response as a smoke check.
- **Performance/budget note:** no real tracing exporter, no real LLM/Tectonic,
  Redis is fakeredis or the shared test instance with `PING` only; metrics
  assertions read the in-process registry (microseconds). The middleware adds one
  contextvar set + one log line per request — negligible.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`).
- [ ] New env vars documented in `.env.example`; observability ADR + field/metric
      reference added under `docs/`.
- [ ] No Overleaf code copied.
