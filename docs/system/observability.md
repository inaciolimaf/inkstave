# Observability

What operators can see of a running Inkstave: structured logs with correlation ids, Prometheus
metrics, optional OpenTelemetry tracing, and health and readiness probes. Spec 51, later hardened by
specs 52 and 55.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/core/observability/log.py` | `JsonLogFormatter`, `ConsoleFormatter`, `redact`, `configure_logging` (the one in use) |
| `backend/src/inkstave/core/observability/context.py` | Correlation context vars, `bind_context`, `clear_context`, `current_context` |
| `backend/src/inkstave/core/observability/middleware.py` | `RequestContextMiddleware`: request id, finish log, HTTP metrics |
| `backend/src/inkstave/core/observability/metrics.py` | Metric catalogue and helpers |
| `backend/src/inkstave/core/observability/tracing.py` | Optional OpenTelemetry setup, `current_trace_id` |
| `backend/src/inkstave/core/logging.py` | `get_request_id`, `set_request_id`; also a legacy `configure_logging` |
| `backend/src/inkstave/core/http/middleware.py` | Legacy `RequestIdMiddleware`, not wired into the app |
| `backend/src/inkstave/modules/admin/routes/health.py` | Probes and `/metrics` |
| `backend/tests/unit/test_observability.py` | Redaction, formatter, context, metrics helpers |
| `backend/tests/integration/test_observability_api.py` | The HTTP surface |
| `backend/tests/integration/test_health.py` | Probe behaviour |

## Routes

All live at the application root, outside `/api/v1`, and are excluded from access logs and HTTP
metrics. The last column is what a client sees through `infra/nginx/default.conf`.

| Method and path | What it does | Errors | Through nginx |
|---|---|---|---|
| `GET /health` | Liveness. `{"status":"ok"}`, touches no dependency | none | SPA `index.html`, 200 |
| `GET /healthz` | Same as `/health` | none | Answered by nginx itself, `ok`, never reaches the backend |
| `GET /ready` | Redis only, 0.5 s bound | 503 `{"status":"not_ready","checks":{...}}` | SPA `index.html`, 200 |
| `GET /readyz` | Database and Redis, `READINESS_CHECK_TIMEOUT_S` per check | 503 `{"status":"not_ready","checks":{...}}` | SPA `index.html`, 200 |
| `GET /metrics` | Prometheus text; samples queue depth first | 404 with `METRICS_PUBLIC=false` | 404 from nginx |

The probes return plain JSON, not the error envelope. `/metrics` is outside the OpenAPI schema.
The probes that matter are reached inside the compose network, on the backend's port 8000. The
backend healthcheck in `backend/Dockerfile` and `docker-compose.prod.yml` calls `/health`. The
frontend healthcheck calls nginx's own `/healthz`.

## How it works

### Logging

`create_app()` and the worker's `startup` both call `configure_logging` from
`backend/src/inkstave/core/observability/log.py`. It replaces the root handlers with one stdout
handler. Repeated calls do not stack.

`LOG_FORMAT=json` (default) emits one JSON object per line:

| Field | Source |
|---|---|
| `timestamp`, `level`, `logger`, `message` | The record; level is lowercase, timestamp is UTC with `Z` |
| `service`, `env` | `SERVICE_NAME`, `Settings.env_name` (`development`, `test`, `production`) |
| `request_id`, `trace_id`, `user_id`, `project_id`, `ws_session_id`, `job_id`, `job_name` | Context vars, only when bound |
| call-site `extra` | Any non-reserved attribute on the record |
| `error.type`, `error.stack` | With `exc_info`; the stack only with `LOG_STACKS=true` |

`LOG_FORMAT=console` prints level, logger, request id and message, for development.

### Correlation

`RequestContextMiddleware` is the outermost middleware, pure ASGI so the context vars reach
downstream code. For each HTTP request it:

1. Reads the `REQUEST_ID_HEADER` header. It keeps the value only if it matches
   `^[A-Za-z0-9._-]{1,128}$`, otherwise it generates a `uuid4` hex.
2. Binds `request_id` and `trace_id`. `trace_id` is the OpenTelemetry trace id when tracing is on,
   otherwise the request id.
3. Echoes the id on the response.
4. On finish calls `_record`: `logger.info("request")` on `inkstave.access`, or `logger.error("request
   failed")` with the traceback, plus `observe_http`.

The finish log carries `http.method`, `http.path`, `http.status_code` and `http.duration_ms`.
`http.path` is the route template from `_route_template`, never the raw URL, which bounds metric
cardinality and keeps ids out of logs. Unmatched paths become `<unmatched>`.

Other bindings:

- Token resolution: `user_id`, in `backend/src/inkstave/modules/auth/deps.py`.
- Collaboration WebSocket: `ws_session_id`, `user_id`, `project_id`, for the whole connection.
- ARQ jobs: `job_id`, `job_name`, `request_id`, `trace_id`, in `run_compile`, `run_agent_turn` and
  `import_project_zip`.

### Redaction

`redact` walks the log payload and replaces the value of any key containing `password`,
`authorization`, `secret`, `api_key`, `api-key`, `access_key` or `cookie` with `***REDACTED***`,
case-insensitive, through dicts, lists and tuples. It applies only in `JsonLogFormatter`.

`token` is left out on purpose, so `tokens_prompt` survives.

### Metrics

`_metric` makes definitions safe to re-import. Prometheus appends `_total` to counters in the
exposition.

| Metric | Type | Labels | Recorded by |
|---|---|---|---|
| `inkstave_http_requests` | Counter | `method`, `path`, `status` | API, `observe_http` |
| `inkstave_http_request_duration_seconds` | Histogram | `method`, `path` | API, `observe_http` |
| `inkstave_ws_connections_active` | Gauge | `kind` | API, `track_ws("collab")` |
| `inkstave_ws_messages` | Counter | `direction`, `kind` | nothing |
| `inkstave_build_info` | Gauge | `version`, `git_sha` | API, `set_build_info` |
| `inkstave_rate_limit_errors` | Counter | `policy` | API, `inc_rate_limit_error` |
| `inkstave_job_queue_depth` | Gauge | `queue` | API, `sample_queue_depth` at scrape time |
| `inkstave_compile_duration_seconds` | Histogram | `engine`, `status` | Worker, `observe_compile` |
| `inkstave_compile` | Counter | `status` | Worker, `observe_compile` |
| `inkstave_job_duration_seconds` | Histogram | `job_name`, `status` | Worker, `track_job` |
| `inkstave_agent_requests` | Counter | `status` | Worker, `inc_agent_request` |
| `inkstave_agent_tokens` | Counter | `direction`, `model` | Worker, `inc_agent_tokens` |

`inc_agent_tokens` maps any model outside `_MODEL_ALLOWLIST` to `other`, which bounds the label.
`track_job` is used by `run_compile` and `import_project_zip`.

Histogram buckets stop at 10 s (`_DURATION_BUCKETS`), shared by HTTP, compile and jobs.

### Tracing

`setup_tracing` is a no-op unless `OTEL_ENABLED=true`, and nothing from `opentelemetry` is imported
otherwise. When on it builds a `TracerProvider` with an OTLP gRPC exporter and calls
`FastAPIInstrumentor.instrument_app`. Any failure logs and continues without tracing.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Denylisted keys are redacted, nested and case-insensitive; `tokens_prompt` is not | `backend/tests/unit/test_observability.py::test_redact_removes_denylisted_keys_case_insensitive_and_nested` |
| One-line JSON with the schema and bound context | `backend/tests/unit/test_observability.py::test_formatter_emits_single_line_json_with_schema_and_context` |
| Unbound context fields are omitted | `backend/tests/unit/test_observability.py::test_formatter_omits_unbound_context_fields` |
| Context does not leak between requests | `backend/tests/unit/test_observability.py::test_bind_and_clear_context_no_leak_between_requests` |
| The request id round-trips and the finish log carries it | `backend/tests/integration/test_observability_api.py::test_request_id_roundtrip_and_finish_log` |
| A malformed inbound request id is replaced | `backend/tests/integration/test_observability_api.py::test_malformed_inbound_request_id_is_replaced` |
| The finish log carries `user_id` after auth | `backend/tests/integration/test_observability_api.py::test_authenticated_finish_log_auto_propagates_user_id` |
| `http.path` is the template, not the raw id | `backend/tests/integration/test_observability_api.py::test_finish_log_http_path_is_route_template_not_raw_id` |
| Unknown paths become `<unmatched>` | `backend/tests/unit/test_observability.py::test_route_template_returns_unmatched_for_unknown_path` |
| `/metrics` serves the catalogue with the pinned content type | `backend/tests/integration/test_observability_api.py::test_metrics_endpoint` |
| `/metrics` survives Redis going down at scrape | `backend/tests/integration/test_observability_api.py::test_metrics_survives_redis_down_at_scrape` |
| The model label is bounded | `backend/tests/unit/test_observability.py::test_agent_token_helper_increments_with_model_allowlist` |
| `track_job` records status even on an exception | `backend/tests/unit/test_observability.py::test_track_job_records_status_even_on_exception` |
| The WebSocket gauge returns to baseline on an exception | `backend/tests/unit/test_observability.py::test_track_ws_gauge_returns_to_baseline_on_exception` |
| `/healthz` stays 200 while `/readyz` goes 503 and recovers | `backend/tests/integration/test_observability_api.py::test_healthz_always_ok_and_readyz_503_then_recovers` |
| `/ready` answers 503 on a raising or hanging Redis | `backend/tests/integration/test_health.py::test_ready_503_when_redis_raises`, `backend/tests/integration/test_health.py::test_ready_503_when_redis_hangs` |
| `/ready` ignores the database | `backend/tests/integration/test_health.py::test_ready_ignores_broken_db` |
| `/readyz` answers 503 on a broken database | `backend/tests/integration/test_health.py::test_readyz_503_when_db_broken` |
| nginx blocks `/metrics` with no upstream | `backend/tests/unit/test_docker_packaging.py::test_nginx_blocks_metrics_without_upstream` |
| A 500 has no request id | no test asserts it; `backend/tests/integration/test_error_envelope_runtime.py::test_500_envelope_does_not_leak_internals` passes `require_request_id=False` |

## Settings

| Variable | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Root logger level |
| `LOG_FORMAT` | `json` | `json` or `console` |
| `LOG_STACKS` | `true` | Include `error.stack` |
| `SERVICE_NAME` | `inkstave-backend` | `service` field |
| `REQUEST_ID_HEADER` | `X-Request-ID` | Inbound and outbound header; also allowed by CORS |
| `APP_VERSION`, `GIT_SHA` | `0.0.0`, `unknown` | `inkstave_build_info` |
| `METRICS_PUBLIC` | `true` | `false` makes the app answer 404 on `/metrics` |
| `OTEL_ENABLED` | `false` | Turns tracing on |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP target |
| `OTEL_SERVICE_NAME` | `inkstave-backend` | Resource name |
| `READINESS_CHECK_TIMEOUT_S` | `2.0` | Per-check bound of `/readyz` and `doctor` |
| `LOG_JSON` | `true` | No effect; see below |

## Points of attention

- **`/health`, `/ready` and `/readyz` answer 200 through nginx whatever the backend's state.**
  nginx proxies only `/api/` and `/ws/`, so these fall through to the SPA fallback and return
  `index.html`. `/healthz` is answered by nginx too. An external monitor pointed at the public URL
  learns only that nginx is up. There is no public route to the backend's probes.
- **Worker metrics never reach a scrape.** `compile`, `job` and `agent` metrics are recorded in the
  worker process, and Prometheus state is per process. The worker exposes no HTTP endpoint: there is
  no `start_http_server`. `/metrics` on the API serves these names with no samples.
  `backend/tests/integration/test_observability_api.py::test_metrics_endpoint` only checks that the
  names appear.
- **`inkstave_job_queue_depth` reads the wrong key.** `sample_queue_depth` defaults to `arq:queue`,
  the only way `health.py` calls it. `WorkerSettings.queue_name` is `COMPILE_QUEUE_NAME`, default
  `compiles`, so the gauge stays 0.
- **`inkstave_ws_messages` is never incremented.**
- **A 500 has no correlation.** The `Exception` handler runs in Starlette's `ServerErrorMiddleware`,
  outside every user middleware. By then `RequestContextMiddleware` has cleared the context. Verified
  by a probe: the body has `request_id: null` and the response has no `X-Request-ID`, no security
  headers and no CORS headers. The finish log does carry the id, so correlate from there.
- **Redaction looks at keys only.** A secret inside a message string, or a key without a listed
  substring (for example `token`), is logged as is. `ConsoleFormatter` does not redact at all.
- **The WebSocket token is in the URL.** The collab handshake passes `?token=`. `http.path` is safe,
  but nginx's default access log records the request line with the query string. See
  [collab.md](collab.md).
- **Two logging modules.** `configure_logging` and `RequestIdFilter` in
  `backend/src/inkstave/core/logging.py` are called by nothing in `backend/src`; only
  `backend/tests/unit/test_logging.py` uses them. `LOG_JSON` feeds only that dead path, yet
  `docker-compose.prod.yml` sets it, and `python-json-logger` is a runtime dependency only for it.
  Use `LOG_FORMAT`.
- **`RequestIdMiddleware` is dead code.** `backend/src/inkstave/core/http/middleware.py` says so
  itself; only `backend/tests/unit/test_request_id_middleware.py` imports it. Unlike the real
  middleware, it accepts any inbound id without validation.
- **Uvicorn logs too.** Its own access log is separate from `inkstave.access` and is not JSON.
- **`/ready` and `/readyz` differ on purpose.** `/ready` stays Redis-only with a fixed 0.5 s bound
  (`READY_TIMEOUT_SECONDS`), kept from spec 02.
- **`OTEL_ENABLED=true` does nothing on a stock image.** No `opentelemetry` package is in
  `backend/pyproject.toml`, so `setup_tracing` hits `ImportError`, logs it and continues.
- **`reset_all` is unused.** Its docstring says job and WebSocket boundaries use it; they use
  `clear_context`.
- **Slow compiles lose histogram precision.** Anything over 10 s lands in `+Inf`, and
  `TECTONIC_COMPILE_TIMEOUT_S` defaults to 60.
- **`METRICS_PUBLIC` defaults to true.** The route has no authentication. In production only nginx's
  block keeps it private, so anything reaching port 8000 can read it.
