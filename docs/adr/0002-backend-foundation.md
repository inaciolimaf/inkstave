# ADR 0002 — Backend foundation: logging, settings, error envelope

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 02 — Backend Foundation

## Context

Spec 02 turns the empty `backend/` skeleton into a runnable FastAPI app. Three
cross-cutting decisions shape every later feature and so are recorded here:
the structured-logging library, how configuration is modelled, and the shape of
error responses.

## Decisions

### 1. Structured logging via `python-json-logger` over stdlib `logging`

We configure the standard-library `logging` module with a single stdout handler
using `python-json-logger`'s `JsonFormatter`, rather than adopting `structlog`.

- It plugs directly into stdlib `logging`, so logs from FastAPI, Uvicorn,
  SQLAlchemy (spec 03) and any third-party library flow through one pipeline
  with one format — no dual logging systems to reconcile.
- The per-request correlation id is injected by a `logging.Filter`
  (`RequestIdFilter`) that reads a `ContextVar`, keeping request context out of
  every call site.
- It is lightweight and has no opinionated processor pipeline to learn.
- Trade-off: `structlog` offers nicer ergonomics for binding structured context,
  but the stdlib-native approach is simpler and integrates third-party logs more
  cleanly. We can revisit with a new ADR if richer context-binding is needed.

Each JSON line carries at least `timestamp`, `level`, `name`, `message`, and
`request_id` (null outside a request). A console formatter is used when
`LOG_JSON=false` for local readability.

### 2. Configuration via `pydantic-settings` (a single typed `Settings`)

All configuration lives in one `Settings(BaseSettings)` object, loaded from the
environment / `.env`, validated at startup, and reached through an `lru_cache`d
`get_settings()` (the single construction point) plus a `get_settings_dep`
FastAPI dependency.

- One typed, validated source of truth; misconfiguration fails fast and loudly.
- `cors_origins` accepts either a comma-separated string or a JSON array (a
  `field_validator` + `NoDecode`) so `.env` files stay human-friendly.
- `database_url` is optional here (reserved for spec 03) so the app never fails
  to construct in environments — e.g. tests — that don't set it.
- Request code never reads `os.environ`; it depends on settings, which keeps
  handlers testable and configuration discoverable.

### 3. A single error envelope + `AppError` hierarchy

Every error response — validation (422), typed `AppError` subclasses (4xx/5xx),
and unhandled exceptions (500) — shares one shape:

```json
{ "error": { "type": "...", "message": "...", "details": [...], "request_id": "..." } }
```

- Clients parse one structure for all failures; `type` is a stable,
  machine-readable, snake_case code.
- `AppError` subclasses (`BadRequestError`, `NotFoundError`, …) let feature code
  raise intent, decoupled from HTTP plumbing; handlers map them to the envelope.
- The catch-all handler logs the full traceback but returns only a generic
  message (the exception class name is appended **only** when `DEBUG=true`), so
  internals never leak to clients.
- Every error carries the current `request_id` (in body and response header) for
  correlation with logs.

## Consequences

- New runtime deps: `fastapi`, `uvicorn[standard]`, `pydantic`,
  `pydantic-settings`, `redis>=5`, `python-json-logger`.
- The lifespan opens/closes the Redis pool and is structured so spec 03 can add
  the DB engine beside it without a rewrite.
- `RequestIdMiddleware` is pure ASGI (not `BaseHTTPMiddleware`) so the
  request-id `ContextVar` stays visible to endpoints, handlers and the access
  log without task-isolation surprises.
- Test tooling (`pytest`, `pytest-asyncio`, `httpx`, `fakeredis`) is introduced
  now because this spec ships tests; spec 04 formalises the testing foundation.

## Alternatives considered

- **`structlog`** — powerful, but a second logging paradigm alongside stdlib;
  rejected for integration simplicity (revisit if needed).
- **Plain env reads / a settings module of constants** — no validation, no
  typing; rejected in favour of `pydantic-settings`.
- **Per-exception ad-hoc JSON responses** — inconsistent client contract;
  rejected in favour of one enforced envelope.
