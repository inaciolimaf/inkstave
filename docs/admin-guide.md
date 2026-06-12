# Inkstave — Admin / Operations Guide

How to deploy, configure, and operate an Inkstave instance. For local
development see [CONTRIBUTING.md](../CONTRIBUTING.md); for end-user features see
the [User Guide](user-guide.md); for how the pieces fit together see the
[Architecture](architecture.md).

## Deployment

Inkstave runs as a set of small Alpine containers orchestrated by
`docker-compose.prod.yml` (spec 56) behind an nginx reverse proxy. Two images are
built from the repo root:

- `inkstave-backend` (`backend/Dockerfile`) — runs the **API**, the **ARQ
  worker**, and the in-app **collab WebSocket**; they differ only by the compose
  `command`. It bundles the Tectonic LaTeX engine.
- `inkstave-frontend` (`frontend/Dockerfile`) — builds the SPA and serves it from
  nginx, which also reverse-proxies `/api` and `/ws` to the backend.

```bash
cp .env.example .env          # then edit (see Configuration below)
docker compose -f docker-compose.prod.yml up -d --build
```

Services: `postgres`, `redis`, `backend`, `worker`, `frontend`. Only the
**frontend** publishes a host port (`PUBLIC_HTTP_PORT`, default `80`); the backend
and worker are reachable only on the internal network. nginx routes `/` → SPA,
`/api` → backend, `/ws` → backend (WebSocket upgrade), and blocks `/metrics`.

**TLS** is the operator's responsibility: terminate it in a proxy/load balancer in
front of the published port. The compose listens on plain HTTP internally.

## Configuration (environment variables)

All configuration comes from environment variables (via `.env`); nothing is baked
into images. The prod compose derives `DATABASE_URL`/`REDIS_URL` from the
`POSTGRES_*` values and the internal service hostnames, and sets the storage and
cache paths itself.

**Required in production** (`ENVIRONMENT=prod`, enforced at boot — the process
refuses to start otherwise): a strong `JWT_SECRET` (≥ 32 bytes), a non-empty
`CORS_ORIGINS` (your public origin), `DATABASE_URL`, and — unless the agent is
stubbed — `OPENROUTER_API_KEY`. Run `python -m inkstave.cli check-config` to
validate before deploying.

The table below documents **every** variable in `.env.example`. Variables prefixed
`POSTGRES_`/`REDIS_`/`DATABASE_`/`REDIS_URL` configure data stores; `JWT_`/`ARGON2_`/
`RATE_LIMIT_`/`CORS_`/`HSTS_`/`TRUST_PROXY_`/`MAX_*` are auth/security; `COMPILE_`/
`TECTONIC_`/`SYNCTEX_`/`LOGPARSE_` are compilation; `COLLAB_`/`HISTORY_` are
collaboration; `AGENT_`/`OPENROUTER_`/`LLM_STUB` are the AI agent; `LOG_`/`OTEL_`/
`METRICS_`/`SERVICE_`/`READINESS_` are observability; `E2E_`/`SUITE_`/`SLOW_TEST_`/
`TEST_` are CI/test-only; `VITE_` are baked into the frontend build.

<!-- 185 variables, generated from .env.example -->
| Variable | Required? | Default | Description | Used by (services) |
| --- | --- | --- | --- | --- |
| `POSTGRES_USER` | No | `inkstave` | Postgres role | postgres, backend, worker |
| `POSTGRES_PASSWORD` | Yes | `inkstave` | Postgres password (dev only — change in prod) | postgres, backend, worker |
| `POSTGRES_DB` | No | `inkstave` | Postgres database name | postgres, backend, worker |
| `POSTGRES_PORT` | No | `5432` | host port mapped to the Postgres container | postgres |
| `REDIS_PORT` | No | `6379` | host port mapped to the Redis container | redis |
| `DATABASE_URL` | Yes | `postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave` | primary async PostgreSQL DSN used by the backend and Alembic | backend, worker |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection used for refresh tokens, presence, and ARQ jobs | backend, worker, collab/websocket |
| `TEST_DATABASE_URL` | No | `postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave_test` | PostgreSQL DSN used only by the integration test suite | tests |
| `ENVIRONMENT` | No | `dev` | dev \| test \| prod | backend, worker, collab/websocket |
| `DEBUG` | No | `false` | verbose errors + SQLAlchemy SQL echo (spec 03) | backend |
| `LOG_LEVEL` | No | `INFO` | DEBUG \| INFO \| WARNING \| ERROR | backend, worker, collab/websocket |
| `LOG_JSON` | No | `true` | JSON logs (true) vs. console (false) | backend, worker, collab/websocket |
| `DOCS_ENABLED` | No | `true` | expose /docs and /redoc | backend |
| `CORS_ORIGINS` | Yes | `http://localhost:5173` | comma-separated or JSON list of origins | backend |
| `REQUEST_ID_HEADER` | No | `X-Request-ID` | request correlation header name | backend |
| `LOG_FORMAT` | No | `json` | json \| console (pretty, dev only) | backend, worker, collab/websocket |
| `LOG_STACKS` | No | `true` | include tracebacks in error logs (false in prod) | backend, worker, collab/websocket |
| `SERVICE_NAME` | No | `inkstave-backend` | `service` log field / build_info | backend, worker, collab/websocket |
| `APP_VERSION` | No | `0.0.0` | inkstave_build_info version | backend |
| `GIT_SHA` | No | `unknown` | inkstave_build_info git_sha (set in CI) | backend |
| `METRICS_PUBLIC` | No | `true` | gate /metrics exposure (bind to internal net in prod) | backend |
| `OTEL_ENABLED` | No | `false` | turn OpenTelemetry tracing on | backend, worker, collab/websocket |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `http://localhost:4317` | OTLP target when enabled | backend, worker, collab/websocket |
| `OTEL_SERVICE_NAME` | No | `inkstave-backend` | OTel resource attribute | backend, worker, collab/websocket |
| `READINESS_CHECK_TIMEOUT_S` | No | `2` | per-dependency /readyz probe timeout (seconds) | backend |
| `DB_POOL_SIZE` | No | `10` | SQLAlchemy async pool size | backend, worker |
| `DB_MAX_OVERFLOW` | No | `5` | extra connections beyond the pool | backend, worker |
| `DB_POOL_TIMEOUT` | No | `30` | seconds to wait for a pooled connection | backend, worker |
| `CACHE_ENABLED` | No | `true` | hot-read Redis cache master switch | backend |
| `CACHE_TTL_SECONDS` | No | `30` | hot-read cache TTL | backend |
| `SUITE_BUDGET_SECONDS` | No | `120` | hard CI gate: fail if the suite exceeds this | tests |
| `SUITE_WARN_SECONDS` | No | `90` | early-warning threshold | tests |
| `SLOW_TEST_WARN_S` | No | `3` | per-test warn threshold | tests |
| `SLOW_TEST_FAIL_S` | No | `10` | per-test fail threshold (non-@slow) | tests |
| `TEST_DB_TEMPLATE` | No | `inkstave_test_tmpl` | template DB name (xdist clone source) | tests |
| `CORS_ORIGINS` | Yes | `http://localhost:5173` | CORS allow-list (CORS_ALLOWED_ORIGINS); never '*' with creds | backend |
| `HSTS_ENABLED` | No | `false` | emit Strict-Transport-Security (true in prod) | backend |
| `TRUST_PROXY_HEADERS` | No | `false` | trust X-Forwarded-For for client IP (only behind a proxy) | backend, collab/websocket |
| `MAX_REQUEST_BODY_BYTES` | No | `1048576` | global JSON body cap (1 MiB) | backend |
| `MAX_UPLOAD_BYTES` | No | `52428800` | per-file upload cap (50 MiB) | backend |
| `RATE_LIMIT_COMPILE` | No | `20/60` | per-user compile cap (limit/window_seconds) | backend |
| `RATE_LIMIT_AGENT` | No | `30/60` | per-user agent cap | backend |
| `RATE_LIMIT_UPLOAD` | No | `60/60` | per-user upload cap | backend |
| `ARGON2_TIME_COST` | No | `3` | iterations | backend |
| `ARGON2_MEMORY_COST` | No | `65536` | KiB of memory | backend |
| `ARGON2_PARALLELISM` | No | `4` | lanes | backend |
| `JWT_SECRET` | Yes | `change-me-dev-only-secret-change-me-0123456789` | HMAC signing secret for access/refresh tokens | backend, collab/websocket |
| `JWT_SECRET_PREVIOUS` | No | `—` | prior signing secret accepted during key rotation | backend, collab/websocket |
| `JWT_ALGORITHM` | No | `HS256` | RS256 is a documented future option | backend, collab/websocket |
| `JWT_ISSUER` | No | `inkstave` | iss claim | backend, collab/websocket |
| `ACCESS_TOKEN_TTL_SECONDS` | No | `900` | access token lifetime (15 min) | backend |
| `REFRESH_TOKEN_TTL_SECONDS` | No | `1209600` | refresh token lifetime / Redis TTL (14 days) | backend |
| `RATE_LIMIT_ENABLED` | No | `true` | master switch for the limiter | backend |
| `RATE_LIMIT_AUTH_LOGIN` | No | `10/300` | login cap, `<limit>/<window_seconds>` per IP+email (legacy alias: `RATE_LIMIT_LOGIN`) | backend |
| `RATE_LIMIT_REGISTER` | No | `5/3600` | per IP | backend |
| `RATE_LIMIT_REFRESH` | No | `30/300` | per IP | backend |
| `RATE_LIMIT_AUTH_PASSWORD` | No | `5/3600` | change-password / sensitive-auth cap, `<limit>/<window_seconds>` per user-or-IP | backend |
| `TRUSTED_PROXY_HEADER` | No | `X-Forwarded-For` | source of the real client IP | backend, collab/websocket |
| `WS_AUTH_CLOSE_CODE` | No | `4401` | WS unauthorized close code (contract, spec 29) | collab/websocket |
| `MAX_DOCUMENT_BYTES` | No | `2000000` | max UTF-8 bytes of a single document | backend, collab/websocket |
| `TECTONIC_BIN` | No | `tectonic` | path/name of the Tectonic executable | worker |
| `TECTONIC_CACHE_DIR` | No | `/var/cache/tectonic` | persistent package cache (mount a volume) | worker |
| `TECTONIC_BUNDLE_URL` | No | `—` | optional pinned bundle; empty = default | worker |
| `TECTONIC_OFFLINE` | No | `false` | true = only cached/bundled packages | worker |
| `COMPILE_WORKDIR_ROOT` | No | `/tmp/inkstave-compiles` | root for per-compile workdirs | worker |
| `TECTONIC_COMPILE_TIMEOUT_S` | No | `60` | wall-clock timeout per compile | worker |
| `COMPILE_MAX_INPUT_FILES` | No | `2000` | assembly file-count cap | worker |
| `COMPILE_MAX_INPUT_BYTES` | No | `104857600` | assembly total-size cap (100 MiB) | worker |
| `TREE_MAX_NODES` | No | `50000` | safety cap on tree nodes materialised per read | api |
| `COMPILE_MAX_OUTPUT_BYTES` | No | `104857600` | output total-size cap (100 MiB) | worker |
| `COMPILE_MAX_LOG_BYTES` | No | `2097152` | captured .log truncation cap (2 MiB) | worker |
| `COMPILE_MAX_STDOUT_BYTES` | No | `262144` | stdout/stderr capture cap (256 KiB) | worker |
| `COMPILE_CPU_SECONDS` | No | `60` | best-effort RLIMIT_CPU (empty disables) | worker |
| `COMPILE_ADDRESS_SPACE_BYTES` | No | `2147483648` | best-effort RLIMIT_AS (empty disables) | worker |
| `COMPILE_KEEP_WORKDIR_ON_FAILURE` | No | `false` | keep failed workdirs for debugging | worker |
| `COMPILE_OUTPUT_PREFIX` | No | `compiles` | storage key prefix for compile outputs | backend, worker |
| `COMPILE_RETAIN_PER_PROJECT` | No | `10` | keep the newest N compiles' outputs per project | worker |
| `COMPILE_RETENTION_MAX_AGE_S` | No | `2592000` | expire outputs older than this (30 days) | worker |
| `COMPILE_RETENTION_SWEEP_S` | No | `3600` | cleanup-job interval | worker |
| `COMPILE_RETENTION_BATCH` | No | `200` | max compiles processed per sweep | worker |
| `COMPILE_PDF_CACHE_MAX_AGE_S` | No | `60` | Cache-Control max-age for the PDF response | backend |
| `COMPILE_MAX_CONCURRENT_PER_PROJECT` | No | `1` | max queued+running compiles per project | backend, worker |
| `COMPILE_MAX_CONCURRENT_PER_USER` | No | `3` | max queued+running compiles per user | backend, worker |
| `COMPILE_DEBOUNCE_COALESCE` | No | `true` | non-force request returns the in-flight compile | backend |
| `COMPILE_JOB_TIMEOUT_S` | No | `120` | ARQ job timeout (must exceed engine timeout) | worker |
| `COMPILE_QUEUE_NAME` | No | `compiles` | ARQ queue / Redis key prefix | backend, worker |
| `COMPILE_SSE_KEEPALIVE_S` | No | `15` | SSE keep-alive comment interval | backend |
| `COMPILE_CANCEL_FLAG_TTL_S` | No | `300` | TTL for the Redis cancel flag | backend, worker |
| `SYNCTEX_MAX_GZ_BYTES` | No | `33554432` | refuse to parse synctex.gz larger than this (32 MiB) | backend |
| `SYNCTEX_INDEX_CACHE_SIZE` | No | `16` | parsed synctex indices cached per process (0 disables) | backend |
| `LOGPARSE_MAX_LOG_BYTES` | No | `8388608` | tail-truncate logs larger than this before parsing (8 MiB) | backend |
| `LOGPARSE_WRAP_WIDTH` | No | `79` | TeX log hard-wrap width used for de-wrapping | backend |
| `LOGPARSE_MAX_PROBLEMS` | No | `1000` | cap on the number of problems returned | backend |
| `COLLAB_SNAPSHOT_EVERY_UPDATES` | No | `200` | compact the CRDT log after this many updates | collab/websocket |
| `COLLAB_SNAPSHOT_INTERVAL_SECONDS` | No | `30` | or after this many seconds since the last snapshot | collab/websocket |
| `COLLAB_TEXT_FLUSH_DEBOUNCE_MS` | No | `1000` | debounce for flushing CRDT text into spec-13 content | collab/websocket |
| `COLLAB_IDLE_EVICT_SECONDS` | No | `300` | drop idle in-memory CRDT docs after this long | collab/websocket |
| `COLLAB_MAX_UPDATE_BYTES` | No | `1048576` | reject a single CRDT update larger than this (1 MiB) | collab/websocket |
| `COLLAB_WS_MAX_FRAME_BYTES` | No | `1048576` | max inbound WebSocket frame size | collab/websocket |
| `COLLAB_WS_SEND_QUEUE_MAX` | No | `256` | bounded per-connection send buffer | collab/websocket |
| `COLLAB_WS_SLOW_CLIENT_TIMEOUT_MS` | No | `2000` | slow-consumer enqueue timeout | collab/websocket |
| `COLLAB_WS_MAX_MSGS_PER_SEC` | No | `200` | inbound message rate guard per connection | collab/websocket |
| `COLLAB_WS_PING_INTERVAL_SECONDS` | No | `25` | idle ping interval (delegated to the ASGI server) | collab/websocket |
| `COLLAB_WS_PONG_TIMEOUT_SECONDS` | No | `10` | pong timeout before close (delegated to the ASGI server) | collab/websocket |
| `COLLAB_REDIS_CHANNEL_PREFIX` | No | `collab:doc:` | Redis pub/sub channel prefix (one per document) | collab/websocket |
| `FRONTEND_URL` | No | `http://localhost:5173` | base for invite accept links (/invite/{token}) | backend |
| `INVITE_TTL_DAYS` | No | `14` | pending invite lifetime | backend |
| `EMAIL_CHANGE_TOKEN_TTL` | No | `86400` | email-change confirmation token lifetime (spec 59) | backend |
| `COMPILE_ALLOWED_FOR_VIEWERS` | No | `true` | viewers may trigger/read compiles | backend |
| `HISTORY_CAPTURE_ENABLED` | No | `true` | observe the CRDT stream into version history | collab/websocket |
| `HISTORY_DEBOUNCE_MS` | No | `5000` | idle debounce before flushing buffered updates | collab/websocket |
| `HISTORY_FLUSH_MAX_BUFFER` | No | `200` | raw updates buffered before a forced flush | collab/websocket |
| `HISTORY_CHUNK_MAX_UPDATES` | No | `100` | captured updates per chunk before sealing + new snapshot | collab/websocket |
| `HISTORY_INLINE_MAX_BYTES` | No | `65536` | payloads/snapshots above this offload to blob storage | collab/websocket |
| `HISTORY_COMPACT_MIN_UPDATES` | No | `50` | min updates before the sweep compacts a doc | worker |
| `HISTORY_COMPACT_MERGE_BYTES` | No | `4096` | adjacent updates smaller than this may be merged | worker |
| `HISTORY_COMPACT_INTERVAL_S` | No | `300` | compaction sweep interval (mocked in tests) | worker |
| `HISTORY_BLOB_PREFIX` | No | `history/` | blob-storage key prefix for offloaded history | backend, collab/websocket |
| `HISTORY_DIFF_MAX_BYTES` | No | `2097152` | max reconstructed text per diff side before 413 | backend |
| `HISTORY_VERSIONS_PAGE_MAX` | No | `200` | upper bound for the versions list `limit` (set false for editor+) | backend |
| `OPENROUTER_API_KEY` | Yes | `—` | API key for the OpenRouter-backed LLM client (required unless the agent is stubbed) | backend, worker |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenAI-SDK base URL (swap provider here) | backend, worker |
| `AGENT_MODEL` | No | `openai/gpt-4o-mini` | model id passed to the SDK | backend, worker |
| `AGENT_TEMPERATURE` | No | `0.2` | default sampling temperature | backend, worker |
| `AGENT_MAX_ITERATIONS` | No | `8` | hard cap on plan loops per turn | backend, worker |
| `AGENT_MAX_TOTAL_TOKENS` | No | `60000` | hard cap on accumulated tokens per turn | backend, worker |
| `AGENT_MAX_TOKENS_PER_CALL` | No | `1024` | max_tokens per LLM call | backend, worker |
| `AGENT_REQUEST_TIMEOUT_S` | No | `60` | per-call timeout for the real client | backend, worker |
| `AGENT_HTTP_REFERER` | No | `https://inkstave.local` | OpenRouter HTTP-Referer header | backend, worker |
| `AGENT_APP_TITLE` | No | `Inkstave` | OpenRouter X-Title header | backend, worker |
| `AGENT_TOOL_READ_MAX_CHARS` | No | `40000` | char cap for read_file output (spec 42) | backend, worker |
| `AGENT_TOOL_SEARCH_MAX_RESULTS` | No | `50` | upper bound for search_project.max_results | backend, worker |
| `AGENT_TOOL_TREE_MAX_NODES` | No | `500` | node cap for list_tree | backend, worker |
| `AGENT_TOOL_EDIT_MAX_CHARS` | No | `200000` | char cap for propose_edit.new_text | backend, worker |
| `AGENT_DIFF_CONTEXT_LINES` | No | `3` | unified-diff context lines per hunk (spec 43) | backend, worker |
| `AGENT_DIFF_MAX_DOC_CHARS` | No | `400000` | refuse to diff documents larger than this | backend, worker |
| `AGENT_STREAM_TRANSPORT` | No | `sse` | sse \| ws (spec 44) | backend |
| `AGENT_STREAM_HEARTBEAT_S` | No | `15` | SSE heartbeat interval | backend |
| `AGENT_RUN_TTL_S` | No | `900` | TTL for per-run last-event + cancel keys | backend, worker |
| `AGENT_MAX_MESSAGE_CHARS` | No | `8000` | max user message length | backend |
| `AGENT_CONTEXT_TOKEN_BUDGET` | No | `8000` | select_context token budget (spec 48) | backend, worker |
| `AGENT_CONTEXT_SURROUNDING_LINES` | No | `40` | context lines around a located section | backend, worker |
| `AGENT_SECTION_EXTRA_COMMANDS` | No | `—` | extra sectioning command names (comma-separated) | backend, worker |
| `AGENT_CONTEXT_CACHE` | No | `memory` | memory \| redis \| off | backend, worker |
| `AGENT_MAX_RUNS_PER_MINUTE_PER_USER` | No | `10` | per-user agent run-rate cap (runs per minute) | backend, worker |
| `AGENT_MAX_CONCURRENT_RUNS_PER_USER` | No | `2` | max simultaneous agent runs per user | backend, worker |
| `AGENT_MAX_RUNS_PER_MINUTE_PER_PROJECT` | No | `20` | per-project agent run-rate cap (runs per minute) | backend, worker |
| `AGENT_MAX_TOKENS_PER_RUN` | No | `120000` | hard token cap for a single agent run | backend, worker |
| `AGENT_MAX_COST_PER_RUN_USD` | No | `0.50` | hard USD cost cap for a single agent run | backend, worker |
| `AGENT_MAX_TOKENS_PER_DAY_PER_PROJECT` | No | `2000000` | daily token budget per project | backend, worker |
| `AGENT_MAX_COST_PER_DAY_PER_USER_USD` | No | `10.00` | daily USD cost budget per user | backend, worker |
| `AGENT_MODEL_COST_TABLE` | No | `{"openai/gpt-4o-mini":{"input":0.00015,"output":0.0006}}` | per-model input/output token prices (USD per 1K tokens) for cost accounting | backend, worker |
| `AGENT_AUDIT_RETENTION_DAYS` | No | `90` | 0 = keep forever | worker |
| `AGENT_INJECTION_GUARD` | No | `on` | on \| off | backend, worker |
| `EMAIL_BACKEND` | No | `console` | smtp \| console \| file \| resend  (console in dev/tests) | backend, worker |
| `EMAIL_FROM` | No | `Inkstave <no-reply@inkstave.local>` | default From header | backend, worker |
| `EMAIL_FILE_DIR` | No | `./tmp/emails` | output dir for the FileEmailSender | backend, worker |
| `SMTP_HOST` | No | `localhost` | SMTP host (Mailpit: mailpit; Resend: smtp.resend.com) | backend, worker |
| `SMTP_PORT` | No | `587` | SMTP port (Mailpit: 1025; Resend: 587 or 465) | backend, worker |
| `SMTP_USER` | No | `—` | SMTP username (Mailpit: empty; Resend: resend) | backend, worker |
| `SMTP_PASSWORD` | No | `—` | SMTP password (Resend: your RESEND_API_KEY) | backend, worker |
| `SMTP_USE_TLS` | No | `true` | STARTTLS/TLS (Mailpit: false; Resend: true) | backend, worker |
| `RESEND_API_KEY` | No | `—` | Resend API key (re_...); required when `EMAIL_BACKEND=resend` | backend, worker |
| `APP_BASE_URL` | No | `http://localhost` | base for accept_url / reset_url / verify_url in emails | backend, worker |
| `PASSWORD_RESET_TOKEN_TTL` | No | `3600` | password-reset link lifetime (seconds) | backend |
| `EMAIL_VERIFICATION_TOKEN_TTL` | No | `86400` | account email-verification link lifetime (seconds) | backend |
| `NOTIFICATION_INVITE_TTL_DAYS` | No | `30` | TTL for invite notifications | backend |
| `NOTIFICATION_SWEEP_INTERVAL_S` | No | `3600` | expiry sweep interval (mocked in tests) | worker |
| `VITE_NOTIFICATIONS_POLL_INTERVAL_MS` | No | `60000` | frontend bell poll interval | frontend build |
| `VITE_AGENT_ENABLED` | No | `true` | show the AI agent chat panel (spec 46; "false" hides it) | frontend build |
| `FILE_STORAGE_BACKEND` | No | `local` | local \| s3 | backend, worker |
| `FILE_STORAGE_LOCAL_PATH` | No | `./data/files` | base dir for the local backend | backend, worker |
| `MAX_UPLOAD_BYTES` | No | `52428800` | per-file upload limit (50 MB) | backend |
| `ALLOWED_UPLOAD_MIME` | No | `image/png,image/jpeg,image/gif,image/webp,image/svg+xml,application/pdf,text/plain,application/x-bibtex,text/x-bibtex` | comma-separated MIME allow-list for uploads | backend |
| `STORAGE_STREAM_CHUNK_BYTES` | No | `65536` | streaming chunk size | backend, worker |
| `IMPORT_MAX_ZIP_BYTES` | No | `52428800` | max compressed `.zip` upload size for project import (50 MiB) | backend, worker |
| `IMPORT_MAX_UNCOMPRESSED_BYTES` | No | `314572800` | max total uncompressed bytes across kept entries (300 MiB) | worker |
| `IMPORT_MAX_FILE_BYTES` | No | `52428800` | max uncompressed size of any single archive entry (50 MiB) | worker |
| `IMPORT_MAX_ENTRIES` | No | `2000` | max kept (folders+docs+files) entries per import | worker |
| `IMPORT_ALLOWED_EXTENSIONS` | No | `.tex,.bib,.cls,.sty,.bst,.bbx,.cbx,.txt,.md,.csv,.tsv,.json,.yml,.yaml,.xml,.svg,.png,.jpg,.jpeg,.gif,.webp,.pdf,.eps` | extensions allowed inside an imported archive (text ∪ binary) | worker |
| `IMPORT_WORKDIR_ROOT` | No | `/tmp/inkstave-imports` | scratch dir for the bounded temp zip copy | worker |
| `EXPORT_MAX_TOTAL_BYTES` | No | `209715200` | max total (doc + file) bytes for the sync export stream; over this → 413 | backend |
| `EXPORT_ASYNC_ENABLED` | No | `false` | when true, over-threshold projects export via an ARQ artifact instead of 413 (optional) | backend, worker |
| `S3_ENDPOINT_URL` | No | `—` | custom endpoint for MinIO/S3-compatible | backend, worker |
| `S3_REGION` | No | `us-east-1` | S3 region for the s3 storage backend | backend, worker |
| `S3_BUCKET` | No | `—` | S3 bucket name for the s3 storage backend | backend, worker |
| `S3_ACCESS_KEY_ID` | No | `—` | S3 access key id for the s3 storage backend | backend, worker |
| `S3_SECRET_ACCESS_KEY` | No | `—` | S3 secret access key for the s3 storage backend | backend, worker |
| `COMPILE_MODE` | No | `real` | real \| mock — "mock" emits a canned PDF/log (no Tectonic); e2e uses mock | worker |
| `LLM_STUB` | No | `false` | true swaps the agent LLM for a deterministic in-process stub (no network); e2e uses true | backend, worker |
| `E2E_BASE_URL` | No | `http://localhost:4173` | where Playwright points the browser (Vite preview origin) | tests |
| `E2E_API_URL` | No | `http://localhost:8099` | backend origin the e2e frontend talks to | tests |
| `E2E_DATABASE_URL` | No | `postgresql+asyncpg://inkstave:inkstave@localhost:5433/inkstave_e2e` | docker-compose.test.yml Postgres | tests |
| `E2E_REDIS_URL` | No | `redis://localhost:6380/0` | docker-compose.test.yml Redis | tests |
| `E2E_PLAYWRIGHT_WORKERS` | No | `—` | parallel workers (blank = from cores) | tests |
| `E2E_RETRIES` | No | `—` | flake retries (blank = 1 in CI, 0 local) | tests |
| `PUBLIC_HTTP_PORT` | No | `80` | host port published by the nginx frontend container | frontend, nginx |
| `MIGRATE_ON_START` | No | `false` | strict: refuse to start unless the DB is at head. | backend |

## First run

1. **Migrations** (spec 57) — run once, before app services accept traffic:
   `docker compose -f docker-compose.prod.yml run --rm backend python -m inkstave.cli migrate`.
   The runner takes a Postgres advisory lock, so concurrent service starts are
   safe (only one migrates). With `MIGRATE_ON_START=false` (the default) the app
   refuses to start unless the DB is already at head.
2. **Admin bootstrap** — create the first admin once (idempotent):
   `INKSTAVE_ADMIN_EMAIL=… INKSTAVE_ADMIN_PASSWORD=… python -m inkstave.cli bootstrap-admin`,
   or `POST /api/setup/admin` (locks after the first admin; `GET /api/setup/status`
   reports `needs_setup`). Unset the admin env vars after first run.
3. **Optional demo data** — `python -m inkstave.cli seed --demo` (never in
   production without `--force`; idempotent). Seeds a demo user
   (`demo@example.com` / `demoPassw0rd` — **dev-only credentials**, never enable
   in production) and a multi-file sample project (`main.tex` that `\input`s
   `sections/intro.tex`, plus `references.bib`).
4. **First-run check** — `just doctor` (or `python -m inkstave.cli doctor`)
   reports config validity plus Postgres/Redis reachability and exits non-zero on
   any failure.

## Scaling

Each container is one process, supervised by Docker `restart` + healthchecks.
App services are stateless (all state is in Postgres/Redis/volumes), so you can
scale horizontally: `docker compose -f docker-compose.prod.yml up -d --scale
worker=3`. Redis is the ARQ broker + pub/sub, so multiple workers share the
compile/agent queues and multiple backend replicas relay collab updates across
instances via Redis. The compile concurrency caps
(`COMPILE_MAX_CONCURRENT_PER_*`) and agent limits are per-user/project, not
per-replica.

## Backups & restore

- **Postgres** (`pgdata` volume) — the source of truth. Back up with
  `pg_dump`/`pg_dumpall`; restore with `psql`/`pg_restore`. This holds users,
  projects, documents, CRDT history, agent sessions, and audit logs.
- **Uploaded files** (`uploads` volume, local backend) — back up the volume (or
  use the S3 backend and rely on its durability).
- **Safe to lose** — the `tectonic-cache` volume (re-downloads on demand), Redis
  (broker/cache; queued jobs are best-effort), and the ephemeral per-compile
  workdirs (never put these on a shared volume).

## LaTeX package management

`infra/tectonic/packages.toml` is the single, editable source of truth for the
LaTeX package configuration. Tectonic fetches packages **on demand** into the
`tectonic-cache` volume, so you rarely list packages by hand. The file lets you
pin the bundle, declare a small `prewarm` set (cached for fast/offline first
compiles), and toggle `allow_network_fetch`. It is mounted read-only into the
`backend` and `worker` services, so editing it and running
`docker compose -f docker-compose.prod.yml restart backend worker` applies the
change with **no code rebuild**. See the file's own "How to add a package"
section and [docs/e2e-strategy.md](e2e-strategy.md) for the mock path used in tests.

## Observability

- **Logs** — structured JSON (`LOG_JSON=true`) to stdout, with request/trace ids
  correlated end-to-end (HTTP → jobs → WS). Ship them with your platform's log
  driver. Secrets are redacted.
- **Metrics** — Prometheus metrics at `/metrics`. **This is blocked at the public
  nginx proxy** (returns 404) and should be scraped only on the internal network.
- **Health** — `/health` (liveness, no dependencies) and `/readyz` (readiness;
  503 when Postgres/Redis are down, with per-check timeouts). The containers'
  healthchecks use these.
- **Tracing** — optional OpenTelemetry (`OTEL_ENABLED=true`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`); a true no-op when disabled.

## Upgrades

Migrations are **forward-only** (never auto-downgrade). To upgrade:

1. Pull/build the new images.
2. Run `python -m inkstave.cli migrate` (advisory-locked, idempotent) — as a
   one-shot step before rolling the app.
3. Restart services (`backend`, `worker`, `frontend`). With strict mode the new
   app verifies the DB is at head and refuses to start otherwise.

## Email delivery (spec 103)

All transactional emails (project invite, email-change confirmation, password
reset, account verification) are rendered and sent **asynchronously** by the
worker's `send_email_job`; request handlers only enqueue. The transport is
chosen by `EMAIL_BACKEND`.

**Local development — Mailpit.** `docker-compose.dev.yml` runs a `mailpit`
service; the dev backend/worker are configured with `EMAIL_BACKEND=smtp`,
`SMTP_HOST=host.docker.internal` (or `mailpit`), `SMTP_PORT=1025`, no TLS/auth.
Trigger any email (register, invite, change-email, forgot-password) and view it
at **http://localhost:8025** (or run `just mail`). Tests do **not** need Mailpit —
they use a fake sender.

**Production — Resend over SMTP (no code change).** Set
`EMAIL_BACKEND=smtp`, `SMTP_HOST=smtp.resend.com`, `SMTP_PORT=587` (or `465`),
`SMTP_USER=resend`, `SMTP_PASSWORD=<RESEND_API_KEY>`, `SMTP_USE_TLS=true`.

**Production — Resend native API.** Set `EMAIL_BACKEND=resend` and
`RESEND_API_KEY=re_...`. `check-config`/`doctor` fail fast if the key is empty.

**SPF / DKIM / domain verification.** For real deliverability (so mail is not
flagged as spam), add your sending domain in the Resend dashboard and publish the
DNS records it shows: an SPF `TXT`, the DKIM `CNAME`/`TXT` records, and a
recommended DMARC `TXT` (`v=DMARC1; p=none; rua=...`). Wait for Resend to mark the
domain *verified*, then set `EMAIL_FROM` to an address on that verified domain.
This is configuration only — no code.

**Verify end to end.** `python -m inkstave.cli send-test-email --to you@example.com`
renders and sends one email through whatever `EMAIL_BACKEND` is configured
(Mailpit in dev, Resend/SMTP in prod) and prints a PASS/FAIL line.

**Secrets.** `RESEND_API_KEY` and the SMTP password come from the environment /
secret store; never commit them (`.env` is git-ignored; `.env.example` carries
empty placeholders). The senders never log the key.

**Retries.** `send_email_job` is registered with `max_tries=3`; a failed send
raises so ARQ retries with its default exponential backoff, then gives up and
logs the failure (template + recipient + HTTP status for Resend — never the key).

## Troubleshooting

- **App refuses to start: "Database is not at the latest migration"** — run
  `inkstave migrate`, or set `MIGRATE_ON_START=true` for single-node convenience.
- **Process exits immediately at boot** — a required production secret is missing
  or weak (`JWT_SECRET`, `CORS_ORIGINS`, `DATABASE_URL`). Run
  `inkstave check-config` for the exact list.
- **Compiles time out / fail** — raise `TECTONIC_COMPILE_TIMEOUT_S` (and keep
  `COMPILE_JOB_TIMEOUT_S` strictly larger); check the `tectonic-cache` volume and
  network for first-time package downloads; inspect the compile log/annotations.
- **WebSocket closes immediately (4401) or won't upgrade** — ensure the proxy
  forwards `Upgrade`/`Connection: upgrade` with HTTP/1.1 (the bundled nginx does);
  confirm the JWT is valid (the WS authenticates via a token).
- **Uploads rejected** — check `MAX_UPLOAD_BYTES` and `ALLOWED_UPLOAD_MIME`.
