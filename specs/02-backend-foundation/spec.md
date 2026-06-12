# Spec 02 — Backend Foundation (requirements)

## 1. Summary

This spec turns the empty `backend/` skeleton into a runnable FastAPI
application. It delivers the application factory, environment-driven settings
(Pydantic Settings v2), structured JSON logging, a global exception-handling
layer with a uniform error envelope, liveness/readiness endpoints, CORS, an
`/api/v1` router mount point, an injectable Redis connection provider, and a
clean async lifespan. It is the substrate that the database layer (03) and all
features attach to. No persistence, auth, or jobs yet.

## 2. Context & dependencies

- **Depends on:** spec 01 (repo layout, `backend/` `uv` project, base compose
  with Postgres + Redis, `.env.example`, `ruff`/`mypy` config).
- **Unlocks:** spec 03 (DB session provider plugs into the lifespan + DI), spec
  04 (tests use the app factory + `httpx.AsyncClient`), specs 06+ (routers
  mount under `/api/v1`).
- **Affected areas:** backend, infra (`backend` service is *prepared* for but
  not required to be added to compose here), docs.

## 3. Goals

- An **application factory** `create_app() -> FastAPI` that builds and returns a
  fully configured app (no import-time side effects, testable).
- **Settings** via `pydantic-settings` `BaseSettings`, loaded from environment
  / `.env`, validated at startup, exposed through a cached accessor and a
  FastAPI dependency.
- **Structured JSON logging** configured once at startup, including a
  per-request correlation/request id propagated via middleware.
- **Global exception handling** producing a single, documented error envelope
  for: validation errors (422), known `AppError` subclasses (4xx/5xx), and
  unhandled exceptions (500, no internals leaked).
- **Health endpoints:** `GET /health` (liveness, always cheap) and
  `GET /ready` (readiness, checks dependencies — here, Redis).
- **CORS** configured from settings (allowed origins list).
- **API versioning:** an `/api/v1` `APIRouter` mounted on the app; later specs
  attach feature routers to it.
- **Redis provider:** a connection pool created in lifespan, exposed via a
  typed FastAPI dependency; closed on shutdown.
- **Async lifespan** using FastAPI's `lifespan` context manager (no deprecated
  `@app.on_event`).
- **DI conventions** documented and used consistently (settings, redis, and —
  forward-looking — db session).
- The app serves an **OpenAPI** schema at `/api/v1/openapi.json` and Swagger UI
  at `/docs` (toggleable via settings for production).

## 4. Non-goals (explicitly out of scope)

- Database engine, SQLAlchemy models, sessions, Alembic, migrations (spec 03).
- Authentication, users, JWT, password hashing (specs 06–08).
- ARQ worker process, job enqueueing, or any background jobs (spec 22+). Only
  the Redis *client/pool* is created here.
- Rate limiting, security headers hardening beyond basic CORS (spec 52).
- Metrics/tracing exporters (spec 51) — basic structured logging only.
- Any frontend (spec 09).

## 5. Detailed requirements

### 5.1 Data model (if any)

None. No tables, no ORM. (Spec 03 introduces persistence.) The readiness check
must therefore probe only Redis, not a database, at this stage.

### 5.2 Backend / API (if any)

#### Module layout (under `backend/src/inkstave/`)

```
inkstave/
├── __init__.py             # __version__
├── main.py                 # `app = create_app()`; uvicorn entrypoint target
├── app.py                  # create_app() factory + lifespan
├── config.py               # Settings (pydantic-settings) + get_settings()
├── logging.py              # configure_logging(); request-id handling helpers
├── errors.py               # AppError hierarchy + error envelope model
├── exception_handlers.py   # handlers registered on the app
├── middleware.py           # RequestIdMiddleware (+ access logging)
├── dependencies.py         # FastAPI dependencies (settings, redis)
├── redis_client.py         # create_redis_pool / provider + ping
└── api/
    ├── __init__.py
    ├── router.py           # api_v1 = APIRouter(prefix="/api/v1"); included here
    └── routes/
        └── health.py       # /health and /ready handlers
```

#### `create_app()` (in `app.py`)

- Reads settings via `get_settings()`.
- Calls `configure_logging(settings)` exactly once.
- Instantiates `FastAPI(title="Inkstave API", version=__version__,
  lifespan=lifespan, docs_url=... , openapi_url="/api/v1/openapi.json")`.
- `docs_url`/`redoc_url` enabled only when `settings.docs_enabled` is true.
- Adds `RequestIdMiddleware` and `CORSMiddleware`
  (`allow_origins=settings.cors_origins`, `allow_credentials=True`,
  `allow_methods=["*"]`, `allow_headers=["*"]`).
- Registers exception handlers (from `exception_handlers.py`).
- Includes `api_v1` router.
- Returns the app. No network connections opened at construction time — those
  happen in the lifespan.

#### Lifespan (async context manager)

- **Startup:** create the Redis connection pool, store it on `app.state.redis`,
  and ping it; if the ping fails, log a warning but **do not crash** (the app
  must still start so `/health` works; `/ready` reports the failure).
- **Shutdown:** close the Redis pool gracefully.
- Structure the lifespan so spec 03 can add DB engine creation/disposal beside
  Redis without rewriting it.

#### Settings (`config.py`)

`class Settings(BaseSettings)` with `model_config = SettingsConfigDict(
env_file=".env", env_prefix="", extra="ignore", case_sensitive=False)`.
Fields (name : type — default — meaning):

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `app_name` | `str` | `"Inkstave"` | display name |
| `environment` | `Literal["dev","test","prod"]` | `"dev"` | runtime env |
| `debug` | `bool` | `False` | enable verbose errors/reload locally |
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | root log level |
| `log_json` | `bool` | `True` | JSON vs. console-friendly logs |
| `docs_enabled` | `bool` | `True` | expose `/docs` & `/redoc` |
| `cors_origins` | `list[str]` | `["http://localhost:5173"]` | allowed origins |
| `redis_url` | `str` (from `REDIS_URL`) | `redis://localhost:6379/0` | Redis DSN |
| `database_url` | `str` (from `DATABASE_URL`) | (required, no default in prod) | reserved for spec 03 — read but unused here |
| `request_id_header` | `str` | `"X-Request-ID"` | inbound/outbound correlation header |

- `get_settings()` is `@lru_cache`d and is the single construction point.
- A FastAPI dependency `get_settings_dep()` returns the cached settings.
- In `environment="test"`, `database_url` may be absent; do not fail at import.

#### Error envelope (`errors.py`)

A single response shape for **all** error responses:

```json
{
  "error": {
    "type": "validation_error",
    "message": "human-readable summary",
    "details": [ { "loc": ["body","field"], "msg": "...", "type": "..." } ],
    "request_id": "0b7c..."
  }
}
```

- Pydantic model `ErrorEnvelope` / `ErrorBody`.
- `class AppError(Exception)` base with attributes `status_code: int`,
  `error_type: str` (snake_case, machine-readable), `message: str`,
  `details: list | None = None`. Provide concrete subclasses now:
  `BadRequestError` (400), `NotFoundError` (404), `ConflictError` (409),
  `UnauthorizedError` (401), `ForbiddenError` (403). (Auth specs will *raise*
  these; they are defined here.)

#### Exception handlers (`exception_handlers.py`)

- `AppError` → its `status_code`, body = envelope with its `error_type`.
- `RequestValidationError` (FastAPI/Pydantic) → `422`,
  `error_type="validation_error"`, `details` = the normalized validation errors.
- `Exception` (catch-all) → `500`, `error_type="internal_error"`, generic
  message (`"Internal server error"`); the full traceback is **logged**, never
  returned. When `settings.debug` is true, include the exception class name in
  `message` for local debugging only.
- Every error response includes the current `request_id`.

#### Middleware (`middleware.py`)

- `RequestIdMiddleware`: read `settings.request_id_header` from the request; if
  absent, generate a UUID4 hex. Store it in a `ContextVar` so the logger and
  exception handlers can read it. Echo it back on the response header.
- Emit one structured access-log line per request (method, path, status,
  duration_ms, request_id) at `INFO`.

#### Endpoints

| Method | Path | Auth | Response | Notes |
| --- | --- | --- | --- | --- |
| GET | `/health` | none | `200 {"status":"ok"}` | liveness; never touches Redis/DB |
| GET | `/ready` | none | `200 {"status":"ready","checks":{"redis":"ok"}}` or `503 {"status":"not_ready","checks":{"redis":"error"}}` | readiness; pings Redis with a short timeout |
| GET | `/api/v1/openapi.json` | none | OpenAPI 3 schema | auto-generated |

- `/health` and `/ready` live at the **root** (not under `/api/v1`) so probes
  are version-independent. The OpenAPI/feature routes live under `/api/v1`.
- `/ready` must use a small timeout (e.g. 500ms) on the Redis ping and convert
  any failure into a `503` with `checks.redis = "error"` — it must not hang or
  raise.

#### Redis provider (`redis_client.py`, `dependencies.py`)

- `async def create_redis_pool(url: str) -> Redis` using `redis.asyncio`
  (`redis>=5` ships asyncio). Configure a connection pool with sane defaults
  and `decode_responses=False`.
- FastAPI dependency `get_redis(request) -> Redis` returns `request.app.state.
  redis`. It raises `AppError` (503-style) if the pool is missing.
- A `ping_redis(redis, timeout) -> bool` helper used by `/ready`.

#### DI conventions (documented in `docs/` and applied)

- Dependencies are plain `Depends(...)` callables in `dependencies.py`.
- Configuration is always reached via `get_settings_dep`, never imported at
  module top-level into request code.
- Connections (Redis now; DB in 03) are created in lifespan and reached via
  `app.state` through a dependency — never created per-request.

### 5.3 Frontend / UI (if any)

None. (Frontend foundation is spec 09.)

### 5.4 Real-time / jobs / external integrations (if any)

- **Redis:** only the connection pool + ping. No pub/sub, no ARQ queue, no
  workers. (ARQ jobs begin in spec 22.)
- No LLM, no Tectonic, no WebSocket.

### 5.5 Configuration

- New runtime deps added to `backend/pyproject.toml`: `fastapi`, `uvicorn[standard]`,
  `pydantic`, `pydantic-settings`, `redis>=5`, and a JSON logging helper
  (`python-json-logger` *or* `structlog` — pick one and record it in an ADR).
- `.env.example` additions (append; do not remove spec 01 rows):

  | Variable | Example | Purpose |
  | --- | --- | --- |
  | `ENVIRONMENT` | `dev` | maps to `Settings.environment` |
  | `DEBUG` | `false` | verbose errors locally |
  | `LOG_LEVEL` | `INFO` | root log level |
  | `LOG_JSON` | `true` | JSON logs on/off |
  | `DOCS_ENABLED` | `true` | expose `/docs` |
  | `CORS_ORIGINS` | `http://localhost:5173` | comma/JSON list of origins |
  | `REQUEST_ID_HEADER` | `X-Request-ID` | correlation header name |

  (`REDIS_URL` and `DATABASE_URL` already exist from spec 01.)
- `justfile` additions: `just dev` → `uv run uvicorn inkstave.main:app
  --reload --app-dir backend/src` (or equivalent); `just run` → non-reload
  variant for prod-like runs.

## 6. Overleaf reference (study only — never copy)

> Read in `../overleaf/` for approach only. Overleaf is Node/Express; Inkstave
> is Python/FastAPI. Concepts transfer; code does not.

- `services/web/app.mjs` — verified present. The web service entrypoint; study
  how the app is bootstrapped and how startup is sequenced. Inkstave's
  equivalent is `app.py`'s `create_app()` + lifespan.
- `services/web/app/src/infrastructure/Server.mjs` — verified present. Study how
  middleware, routers, error handling and locals are wired onto the Express
  app. Inkstave wires the FastAPI app analogously but with its own code.
- `libraries/settings/` (`index.js`, `Settings.js`, `merge.js`) — verified
  present. Study how layered settings/merge work. Inkstave replaces this with
  `pydantic-settings`; take only the *idea* of a single typed settings object.
- `libraries/logger/` (`logging-manager.js`, `serializers.js`,
  `log-level-checker.js`) — verified present. Study structured logging,
  serializers, and dynamic log levels. Inkstave implements its own JSON logging.
- `libraries/o-error/` (`index.cjs`, `README.md`) — verified present. Study the
  error-with-context pattern (tagging errors, causes). Inkstave's `AppError`
  hierarchy + error envelope is the independent equivalent.
- `services/web/app/src/infrastructure/RedisWrapper.mjs` and
  `libraries/redis-wrapper/` — verified present. Study how a single Redis
  client/pool is shared. Inkstave uses `redis.asyncio` via the lifespan.

No Overleaf equivalent for: FastAPI lifespan, Pydantic Settings, or a
FastAPI-style error envelope — design those from the FastAPI docs.

## 7. Acceptance criteria

1. **Given** the backend, **when** I call `create_app()` in a test, **then** it
   returns a `FastAPI` instance with no network I/O performed at construction
   time.
2. **Given** the running app, **when** I `GET /health`, **then** I get `200` and
   body `{"status":"ok"}` regardless of Redis availability.
3. **Given** Redis reachable, **when** I `GET /ready`, **then** I get `200` with
   `checks.redis == "ok"`.
4. **Given** Redis unreachable (or the ping raises), **when** I `GET /ready`,
   **then** I get `503` with `checks.redis == "error"` and the request does not
   hang beyond the configured timeout.
5. **Given** a request that triggers a `RequestValidationError`, **when** it is
   handled, **then** the response is `422` with `error.type ==
   "validation_error"` and a non-empty `error.details`.
6. **Given** a route that raises `NotFoundError`, **when** called, **then** the
   response is `404` with `error.type == "not_found"` and the supplied message.
7. **Given** a route that raises an unexpected `Exception`, **when** called,
   **then** the response is `500` with `error.type == "internal_error"`, a
   generic message, **and** the traceback is present in the logs but **absent**
   from the response body.
8. **Given** any response, **then** it carries the configured request-id header,
   and that same id appears in `error.request_id` for error responses and in the
   access-log line.
9. **Given** an inbound request carrying `X-Request-ID: abc`, **then** the
   response echoes `X-Request-ID: abc` (the provided id is reused).
10. **Given** `settings.log_json == true`, **when** the app logs, **then** each
    log line is valid JSON containing at least `level`, `message`, `request_id`
    (when in request context), and `timestamp`.
11. **Given** an allowed origin in `cors_origins`, **when** a CORS preflight is
    sent, **then** the appropriate `Access-Control-Allow-Origin` header is
    returned; a disallowed origin is not granted.
12. **Given** `docs_enabled == false`, **when** I `GET /docs`, **then** I get
    `404`; **when** `true`, **then** `200`.
13. **Given** the app, **when** I `GET /api/v1/openapi.json`, **then** it returns
    a valid OpenAPI document that documents the error envelope as a component.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Redis is faked; no real network calls; nothing slow.

- **Unit (pytest):**
  - `Settings` loads from a monkeypatched environment; defaults apply; list
    parsing of `cors_origins` works; `get_settings()` is cached.
  - `AppError` subclasses carry the right `status_code`/`error_type`.
  - Logger emits JSON containing required keys (capture via a buffer handler).
  - `RequestIdMiddleware` generates an id when absent and reuses a provided id.
- **Integration (pytest + `httpx.AsyncClient` against `create_app()`):**
  - `/health` → 200.
  - `/ready` → 200 with a **fake** Redis whose `ping()` returns true;
    → 503 with a fake Redis whose `ping()` raises / times out.
  - Validation error path → 422 envelope.
  - A temporary test-only route raising `NotFoundError` → 404 envelope; one
    raising `Exception` → 500 envelope with no traceback leak.
  - Request-id echo and presence in error body.
  - OpenAPI document fetch and component presence.
  - CORS preflight allowed vs. disallowed origin.
  - **Redis is provided by `fakeredis` (aioredis interface) or a hand-rolled
    stub** injected via dependency override / `app.state` — no real Redis,
    no Docker, in the fast suite.
- **E2E (Playwright):** not applicable (no UI yet).
- **Performance/budget note:** all tests are in-process against the ASGI app via
  `httpx.ASGITransport`; no sockets, no containers, no sleeps (timeouts are
  driven through fakes). Expected runtime: a few hundred milliseconds.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (factory, settings, logging, errors,
      handlers, middleware, health/ready, CORS, `/api/v1`, Redis provider,
      lifespan, DI conventions, OpenAPI).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green; Redis faked.
- [ ] Full suite runs in < 2 minutes.
- [ ] `ruff`/`mypy` clean; app starts under `uvicorn` locally.
- [ ] New env vars documented in `.env.example`; ADR for logging/settings choice
      added under `docs/`.
- [ ] No Overleaf code copied.
