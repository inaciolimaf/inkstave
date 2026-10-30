# Overview

Inkstave is a real-time collaborative LaTeX editor with a server-side AI agent. The backend is one
FastAPI process, one ARQ worker process and one CLI, built from the same Python package. This file
covers what those three share: layers, lifecycle, settings, errors, the database, migrations, the
CLI, background tasks, jobs and the test tiers. Specs 01–05, 53, 56, 57, 62, 63.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/main.py`, `backend/src/inkstave/app.py` | Uvicorn target; application factory, lifespan, middleware order |
| `backend/src/inkstave/router.py` | The `/api/v1` router; attaches every feature router |
| `backend/src/inkstave/worker.py` | ARQ `WorkerSettings`, startup and shutdown of the worker context |
| `backend/src/inkstave/compile/worker.py` | Deployment alias: `inkstave.compile.worker.WorkerSettings`, the path compose names |
| `backend/src/inkstave/cli.py` | Operations CLI, installed as `inkstave` |
| `backend/src/inkstave/models.py` | Imports every model so `Base.metadata` is complete for Alembic |
| `backend/src/inkstave/core/config` | `Settings` (`settings.py`, fields in `groups.py`) and `AgentSettings` (`agent.py`) |
| `backend/src/inkstave/core/db` | `Base`, engine, unit of work, `get_owned` (same error for missing and foreign records) |
| `backend/src/inkstave/core/deps.py` | `get_settings_dep`, `get_redis`, `ServiceUnavailableError` |
| `backend/src/inkstave/core/errors.py`, `backend/src/inkstave/core/exception_handlers.py` | `ErrorEnvelope`, `AppError` hierarchy, the handlers |
| `backend/src/inkstave/core/invariants.py`, `backend/src/inkstave/core/schemas.py` | `require()`, a guard that survives `python -O`; `StrictModel`, base of request bodies |
| `backend/src/inkstave/core/tasks.py`, `backend/src/inkstave/core/time.py` | `spawn()`; `Clock` protocol and `SYSTEM_CLOCK` |
| `backend/src/inkstave/core/logging.py`, `backend/src/inkstave/core/observability` | See [observability.md](observability.md) |
| `backend/src/inkstave/core/http` | See [security.md](security.md) |
| `backend/src/inkstave/infra/redis.py`, `backend/src/inkstave/infra/cache.py` | Client helpers; `RedisCache`, fail-soft JSON cache with TTL |
| `backend/src/inkstave/infra/deps.py` | `get_object_store`, `get_email_enqueuer` dependencies |
| `backend/src/inkstave/infra/storage`, `backend/src/inkstave/infra/mailer` | See [documents.md](documents.md), [notifications.md](notifications.md) |
| `backend/migrations` | Alembic environment and revisions |
| `backend/pyproject.toml`, `Makefile` | Import contracts, lint and pytest config; every command, which CI runs |

## Architecture

A modular monolith with three layers, top to bottom: `inkstave.modules`, `inkstave.infra`,
`inkstave.core`. `core` knows no domain. `infra` holds technical services (Redis, cache, storage, mailer). `modules`
holds the domains. The composition root (`app`, `cli`, `main`, `models`, `router`, `worker`) gathers
everything and stays out of the contracts.

Module order, from `[tool.importlinter]` in `backend/pyproject.toml`, top to bottom: `admin` and
`agent` (same level, they may not import each other), `compile`, `history`, `collab`, `projects`,
`notifications`, `auth`. A module may import only what is below it.

Three kinds of rule enforce this:

- **Layers.** Two `layers` contracts: the three layers, and the module order. `make boundaries`
  runs them; `make lint` includes them. `TYPE_CHECKING` imports are excluded.
- **Public interfaces.** One `forbidden` contract per module: others use only what its
  `__init__.py` exports. `admin` exports nothing.
- **Design rules.** `backend/tests/unit/test_architecture.py` covers what import-linter cannot: SQL
  location, session access, at most 8 files per folder, no generic folder names, `__all__` present.

The module order holds three exceptions, each with a "Target:" comment in `backend/pyproject.toml`:

| Import | Why it exists | Stated target |
|---|---|---|
| `inkstave.modules.collab.ws.components -> inkstave.modules.history` | The room builds the history capture service and feeds it each CRDT update | collab emits an update event |
| `inkstave.modules.projects.routes.projects -> inkstave.modules.collab` | Export flushes open rooms first | a domain event, or export moves up |
| `inkstave.modules.projects.routes.projects -> inkstave.modules.compile` | Project deletion sweeps compile outputs | projects emits `ProjectDeleted` |

No domain-event mechanism exists. There is no bus, no `ProjectDeleted`, no subscriber. The targets
are intent only. The `emit` methods in the agent module and the `subscribe` in
`backend/src/inkstave/modules/collab/ws/redis_bridge.py` are SSE and CRDT transport, not domain
events.

## Domain map

| Module | Path | Documented in |
|---|---|---|
| admin | `backend/src/inkstave/modules/admin` | Probes in [observability.md](observability.md); setup and provisioning here and in [auth.md](auth.md) |
| agent | `backend/src/inkstave/modules/agent` | [agent.md](agent.md) |
| auth | `backend/src/inkstave/modules/auth` | [auth.md](auth.md) |
| collab | `backend/src/inkstave/modules/collab` | [collab.md](collab.md) |
| compile | `backend/src/inkstave/modules/compile` | [compile.md](compile.md) |
| history | `backend/src/inkstave/modules/history` | [history.md](history.md) |
| notifications | `backend/src/inkstave/modules/notifications` | [notifications.md](notifications.md) |
| projects | `backend/src/inkstave/modules/projects` | [projects.md](projects.md), [documents.md](documents.md), [sharing.md](sharing.md) |
| frontend | `frontend/src` | [frontend.md](frontend.md) |

## Data

Each table belongs to its domain file. All models inherit `Base`, whose `MetaData` carries
`NAMING_CONVENTION` so constraint names are stable. `TimestampMixin` uses `eager_defaults`, which
prevents a lazy refresh (`MissingGreenlet`) under the async engine.

Connections live on `app.state`: `redis`, `db_engine`, `db_sessionmaker`, `collab`, and `arq_pool`,
which `get_email_enqueuer` creates on first use.

## How it works

### Application lifecycle

`create_app()` does no network I/O. Middleware order, outermost first: `RequestContextMiddleware`,
`SecurityHeadersMiddleware`, `BodySizeLimitMiddleware`, `CORSMiddleware`. Routers: the root probes,
`/api/setup` (not versioned), `/api/v1`, then the collaboration WebSocket at the root.

`lifespan` on startup:

1. `create_redis_pool` (lazy, no connection yet).
2. `_check_redis` pings with `STARTUP_PING_TIMEOUT_SECONDS`. Failure only warns.
3. `_open_database`. Without `DATABASE_URL` it warns and the app runs with no database and no
   collab. Otherwise it builds the engine, runs `check_db` (a failure warns), runs
   `_ensure_migrations`, then `build_collab_components`.

On shutdown `_close_collab` flushes history and stops the room manager, so buffered edits reach the
database; then Redis closes and the engine is disposed.

`_ensure_migrations` is the gate. With `MIGRATE_ON_START=true` it runs `run_upgrade` in a thread.
Otherwise `is_database_at_head` must be true, or startup raises `RuntimeError`.

### Settings

`get_settings()` is `lru_cache`d: the single construction point. Code never reads `os.environ` for
settings (`cli.py` reads `INKSTAVE_ADMIN_EMAIL` and `INKSTAVE_ADMIN_PASSWORD`, which are not
settings; `validate_required_runtime` reads the raw environment on purpose). `.env` is read
relative to the working directory, unknown variables are ignored, names are case-insensitive. List
settings accept JSON or comma-separated text. `CORS_ALLOWED_ORIGINS` and `RATE_LIMIT_AUTH_LOGIN`
have legacy aliases (`CORS_ORIGINS`, `RATE_LIMIT_LOGIN`).

`AgentSettings` is a separate object from `get_agent_settings()`; constructing it needs no API key.

`Settings` construction runs the guards. Boot refusals are listed in [security.md](security.md).
Two are not about secrets: `S3_BUCKET` is required when `FILE_STORAGE_BACKEND=s3`, and
`COMPILE_JOB_TIMEOUT_S` must exceed `TECTONIC_COMPILE_TIMEOUT_S` so the engine timeout fires before
ARQ kills the job.

### Errors

Feature code raises `AppError` subclasses. `register_exception_handlers` installs three handlers.

Each subclass fixes a status and an `error.type`: `BadRequestError` 400 `bad_request`,
`UnauthorizedError` 401 `unauthorized` (adds `WWW-Authenticate: Bearer`), `ForbiddenError` 403
`forbidden`, `NotFoundError` 404 `not_found`, `ConflictError` 409 `conflict`, `GoneError` 410 `gone`,
`RateLimitError` 429 `rate_limited` (adds `Retry-After`, `X-RateLimit-*`), `ServiceUnavailableError`
503 `service_unavailable`. `RequestValidationError` becomes 422 `validation_error` with `details`.
Any other `Exception` becomes 500 `internal_error`: the traceback is logged, never returned.

The body is `{"error": {"type", "message", "details", "request_id"}}`. Domains subclass these with
their own `error_type`. With `DEBUG=true` a 500 message adds the exception class name.

### Database

`create_engine_and_sessionmaker` builds one async engine (`pool_pre_ping`, pool from settings) and
a sessionmaker with `expire_on_commit=False` and `autoflush=False`. The API, the worker and the CLI
each call it once. `normalize_async_dsn` rewrites `postgresql://` and `postgres://` to asyncpg.

**Unit of work.** `UNIT_OF_WORK` in `backend/src/inkstave/core/db/session.py` is
`Depends(get_db_session, scope="function")`: one session per request, committed before the
response leaves. Routes write `session: AsyncSession = UNIT_OF_WORK`. A bare `Depends(get_db_session)`
would commit after the response, so a failed commit would reach the client as a 200, and would open
a second session. A streaming body has no session: it reads what it needs first, or opens a short
one from `get_session_factory`.

**Connection deadlines.** Every application connection carries `lock_timeout`, `statement_timeout`
and `idle_in_transaction_session_timeout`, set as `server_settings`. Migrations do not use this
engine. Two helpers raise a limit for one transaction with `set_config(..., true)`: `allow_idle` and
`allow_long_statements`. Compile assembly commits before Tectonic runs (`on_assembled=session.commit`
in `backend/src/inkstave/worker.py`), so no transaction waits on it.

### Migrations

22 revisions in `backend/migrations/versions`, oldest
`backend/migrations/versions/20260609_1531_d1d4079342b4_create_pings.py`, newest by name
`backend/migrations/versions/20261030_1000_b4d8f1a2c6e3_add_session_revocation.py`. Every schema
change ships one. A released migration is never edited.

`run_upgrade` in `backend/src/inkstave/modules/admin/provisioning/migrate.py` takes a Postgres
advisory lock (`MIGRATION_LOCK_KEY`) on a dedicated psycopg2 connection and runs `alembic upgrade
head`. Concurrent starters block, then run a no-op. It is synchronous because `backend/migrations/env.py`
runs its own `asyncio.run`, so async code calls it through `asyncio.to_thread`. This runner is the
only place synchronous SQLAlchemy is allowed.

### CLI

`python -m inkstave.cli <command>`, or `inkstave <command>`. Stdlib `argparse`. Each command returns
an exit code, so it works as a deploy gate.

| Command | Does | Non-zero when |
|---|---|---|
| `migrate` | `run_upgrade` under the advisory lock | it raises |
| `bootstrap-admin` | Creates the first admin; idempotent. `INKSTAVE_ADMIN_EMAIL`, `INKSTAVE_ADMIN_PASSWORD`, or a TTY prompt | 2 without credentials |
| `seed --demo [--force]` | Demo user and project; refuses in production without `--force` | 2 without `--demo`, 1 on refusal |
| `check-config` | `validate_config` | any problem |
| `doctor` | Config plus Postgres and Redis reachability | any failure |
| `send-test-email --to <addr> [--template <name>]` | One e-mail through the configured backend, without the worker | send or template failure |
| `deactivate-user --email <addr>` | Locks the account out and ends its sessions | no such user |

### Tasks and jobs

`spawn()` in `backend/src/inkstave/core/tasks.py` holds a reference to a background task, since the
event loop only keeps a weak one, and logs its failure. History's idle flush and collab's force
close use it. Work that outlives a process or runs long is an ARQ job.

`arq inkstave.worker.WorkerSettings`, or the alias compose uses. One worker, one queue, named by
`COMPILE_QUEUE_NAME`; compile, e-mail, history, agent and import jobs share it.

| Job | `max_tries` | Timeout | Cron |
|---|---|---|---|
| `run_compile` | 1 | `COMPILE_JOB_TIMEOUT_S` | |
| `send_email_job` | 3 | ARQ default | |
| `compact_history` | 2 | ARQ default | every 5 minutes |
| `sweep_notifications` | 2 | ARQ default | hourly, minute 0 |
| `run_agent_turn` | 1 | `AGENT_JOB_TIMEOUT_S` | |
| `agent_audit_cleanup` | 1 | ARQ default | 03:30 daily |
| `import_project_zip` | 1 | ARQ default | |
| `cleanup_compile_outputs` | ARQ default | ARQ default | from `COMPILE_RETENTION_SWEEP_S` via `_sweep_minutes` |

`startup` configures logging, then fills the context: `settings`, `engine`, `session_factory`,
`redis`, `object_store`, `email_sender`, the compile seams from `_register_compile`, and
`agent_settings`. `_build_runner` picks mock, sandbox or local (see [compile.md](compile.md)).
`shutdown` closes Redis and disposes the engine.

### Test tiers

| Tier | Selected by | Needs | Command |
|---|---|---|---|
| Default backend | `addopts`: `-m 'not slow and not e2e and not live'`, `-n auto` | Postgres for the integration part | `make test` |
| Unit | `UNIT_MARKERS` in `Makefile` | nothing | `make test-unit` |
| Integration | `INTEGRATION_MARKERS` in `Makefile`, the `integration` marker | Postgres; Redis is faked | `make test-integration` |
| E2E | Playwright projects `routes`, `mobile`, `flows`, `smoke`, `full` | `make e2e-infra` | `make e2e-smoke` is what CI runs |
| Real compile | `RUN_REAL_COMPILE=1` and `tectonic` on the path | Tectonic | `backend/tests/smoke/test_real_compile.py` |

The tiers are chosen by marker, not by folder. `backend/tests/conftest.py` adds one structural rule:
a test under `backend/tests/unit` that reaches the `_template_db` fixture fails collection with
`pytest.UsageError`.

**Integration tests skip when Postgres is unreachable.** `_template_db` in
`backend/tests/fixtures/database.py` catches the connection failure and calls `pytest.skip`, so every
dependent test skips and the run stays green. Each xdist worker uses its own database, migrated once
and rolled back per test. `backend/tests/fixtures/env.py` strips the machine's settings before
collection and points `DATABASE_URL` at a refused port, so a test that did not ask for the database
cannot find one. CI enforces a 120 s budget across unit, integration and e2e (`make budget`) and an
80% coverage floor on unit plus integration (`make coverage-combine`).

## Rules and guarantees

| Invariant | Test |
|---|---|
| The session is reached only through `UNIT_OF_WORK` | `backend/tests/unit/test_architecture.py::test_session_dependency_is_only_reached_through_the_unit_of_work` |
| A failed commit is a 500, not a 200 | `backend/tests/unit/test_unit_of_work.py::test_a_failed_commit_is_a_500_not_a_200` |
| The session closes before a streaming body starts | `backend/tests/unit/test_unit_of_work.py::test_the_session_is_closed_before_a_streaming_body_starts` |
| Import exceptions never increase beyond 3 | `backend/tests/unit/test_architecture.py::test_import_exceptions_only_go_down` |
| Routes hold no SQL; SQL goes through the query builder | `backend/tests/unit/test_architecture.py::test_routes_hold_no_sql`, `backend/tests/unit/test_architecture.py::test_sql_only_through_the_query_builder` |
| No synchronous database API outside the migration runner | `backend/tests/unit/test_architecture.py::test_no_synchronous_database_api` |
| Ownership is never compared by hand | `backend/tests/unit/test_architecture.py::test_ownership_is_never_checked_by_hand` |
| Deadlines are set on a real connection | `backend/tests/integration/test_connection_limits.py::test_defaults_are_set_on_a_real_connection` |
| An idle transaction past the limit is killed | `backend/tests/integration/test_connection_limits.py::test_an_idle_transaction_past_the_limit_is_killed` |
| `allow_idle` and `allow_long_statements` end with the transaction | `backend/tests/integration/test_connection_limits.py::test_allow_idle_survives_the_wait_and_ends_with_the_transaction`, `backend/tests/integration/test_connection_limits.py::test_allow_long_statements_only_lasts_for_the_transaction` |
| Migrations do not inherit request limits | `backend/tests/unit/test_external_timeouts.py::test_migrations_do_not_inherit_the_request_limits` |
| Strict mode refuses a database behind head | `backend/tests/unit/test_bootstrap_57.py::test_strict_mode_refuses_to_start_when_db_behind_head` |
| Models and migrations agree | `backend/tests/integration/test_migrations.py::test_autogenerate_is_empty` |
| The 500 body does not leak internals | `backend/tests/integration/test_error_envelope_runtime.py::test_500_envelope_does_not_leak_internals` |
| A spawned task is held and its failure logged | `backend/tests/unit/test_background.py::test_spawn_holds_the_task_until_it_finishes`, `backend/tests/unit/test_background.py::test_spawn_logs_a_failure` |
| The suite ignores the machine's `.env` and database | `backend/tests/unit/test_env_isolation.py::test_dotenv_is_not_read`, `backend/tests/unit/test_env_isolation.py::test_database_is_unreachable_unless_a_test_asks_for_it` |
| `require()`, `RedisCache`, `get_owned`, `_sweep_minutes` | no dedicated test |

## Settings

| Variable | Default | Effect |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev`, `test` or `prod`; `prod` turns on the boot guards |
| `DATABASE_URL` | none | Without it the app runs with no database |
| `REDIS_URL` | `redis://localhost:6379/0` | Shared client and ARQ |
| `MIGRATE_ON_START` | `false` | Migrate at startup instead of refusing |
| `DB_LOCK_TIMEOUT_S` | `10` | `lock_timeout`; 0 turns it off |
| `DB_STATEMENT_TIMEOUT_S` | `30` | `statement_timeout`; 0 turns it off |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT_S` | `120` | Must stay above the slowest call inside a request |
| `COMPILE_QUEUE_NAME` | `compiles` | The one ARQ queue |
| `COMPILE_JOB_TIMEOUT_S` | `120` | Must exceed `TECTONIC_COMPILE_TIMEOUT_S` (`60`) |

## Points of attention

- **Not every error uses the envelope.** No handler covers Starlette's `HTTPException`, so an unknown
  route or a 405 answers `{"detail": ...}`. The middleware's 413 has its own shape; see
  [security.md](security.md). A 500 carries `request_id: null`: see
  [observability.md](observability.md).
- **A database that is down at startup still aborts it.** `check_db` only warns, but
  `_ensure_migrations` then calls `current_revision`, whose `engine.connect()` sits outside its
  `try`. Only Redis failures are truly tolerated at boot.
- **`docker-compose.prod.yml` has no migrate step.** Strict mode is the default, so a stack needs
  `MIGRATE_ON_START=true` in `.env` or a manual `inkstave migrate`. The worker runs no gate at all.
- **`make migrate` skips the advisory lock.** It calls `alembic` directly. `inkstave migrate` takes
  the lock.
- **Skipped integration tests look like success.** Nothing fails a run in which `_template_db`
  skipped.
- **Tier selection trusts the marker.** A file in `backend/tests/integration` without the
  `integration` marker runs in the unit tier. No test currently carries `slow`, `e2e` or `live`.
- **`HISTORY_COMPACT_INTERVAL_S` and `NOTIFICATION_SWEEP_INTERVAL_S` drive nothing.** The cron
  entries are fixed. Only `COMPILE_RETENTION_SWEEP_S` takes effect, read at worker import.
- **`app.state.arq_pool` is never closed** by the lifespan.
- **`docs/adr/0057-cicd-bootstrap.md` describes a CD workflow that does not exist.** It cites a
  `cd.yml`; `.github/workflows/ci.yml` is the only workflow. It also cites pre-move paths.
- **Size debt is frontend only.** `PENDING_SIZE` in `frontend/eslint.config.js` holds 21 files over
  the 100-line function cap. `scripts/lint_function_length.py` (30 lines per function, 300 per file)
  has no exceptions.
