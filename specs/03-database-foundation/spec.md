# Spec 03 — Database Foundation (requirements)

## 1. Summary

This spec wires PostgreSQL into the FastAPI app using **async SQLAlchemy 2.x**
and **Alembic**. It delivers the async engine and session factory (created in
the app lifespan), a declarative `Base` with shared mixins (UUID primary key,
`created_at`/`updated_at`), a metadata-wide constraint **naming convention**, a
transaction-scoped FastAPI session dependency, and a fully configured async
Alembic environment with autogenerate. A single trivial example table proves the
end-to-end migration workflow. No domain models are added here — those come with
their respective features.

## 2. Context & dependencies

- **Depends on:** spec 01 (Postgres compose service, `DATABASE_URL` in
  `.env.example`), spec 02 (app factory, async lifespan, settings, DI pattern,
  `AppError`).
- **Unlocks:** every feature spec that persists data (06 users, 11 projects, 12
  files, …) and spec 04 (test DB fixtures build on this engine/session/Base).
- **Affected areas:** backend, infra (Alembic config + migrations dir), docs.

## 3. Goals

- An **async engine** (`create_async_engine` with `asyncpg`) created once in the
  app lifespan and disposed on shutdown, configured from `settings.database_url`.
- An **`async_sessionmaker`** producing `AsyncSession`s with
  `expire_on_commit=False`.
- A declarative **`Base`** carrying a shared `MetaData` with a constraint
  **naming convention** (so Alembic generates stable, named constraints).
- Reusable **mixins**: `UUIDPrimaryKeyMixin` (UUID v4 PK), `TimestampMixin`
  (`created_at`, `updated_at` with DB-side defaults and `onupdate`).
- A **FastAPI session dependency** `get_db_session()` that yields an
  `AsyncSession`, commits on success, rolls back on exception, and always
  closes — one transaction per request by default.
- **Alembic** configured for **async** with **autogenerate** wired to `Base.
  metadata`, reading the DSN from settings; `script.py.mako` and `env.py`
  authored for async.
- One **example table** (`pings`) and its **initial migration**, proving
  `alembic upgrade head` / `downgrade base` and `autogenerate` all work.
- `/ready` (from spec 02) is **extended** to also check the database with a
  short-timeout `SELECT 1`.

## 4. Non-goals (explicitly out of scope)

- Any domain model (users/projects/files/…); only the `pings` example table.
- The reusable pytest DB fixtures, template-DB strategy, and rollback-per-test
  machinery — those are **spec 04**. Minimal tests here may stand up their own
  ephemeral DB.
- Read replicas, connection multiplexing/pgbouncer, partitioning, or advanced
  pooling tuning (later/perf specs).
- Repository/unit-of-work abstractions beyond the session dependency (features
  may introduce their own patterns, consistent with `CLAUDE.md`).

## 5. Detailed requirements

### 5.1 Data model

#### Conventions (apply to all future tables)

- All tables use a **UUID** primary key named `id` (`uuid.UUID`, server default
  `gen_random_uuid()` via `pgcrypto`/`uuid-ossp`, or generated app-side — pick
  app-side `uuid4()` default to avoid an extension dependency, and document it).
- Timestamps are timezone-aware (`TIMESTAMP WITH TIME ZONE`), `created_at`
  defaults to `now()`, `updated_at` defaults to `now()` and updates on row
  modification.
- **Constraint naming convention** registered on the `MetaData`:

  | Type | Template |
  | --- | --- |
  | `ix` (index) | `ix_%(column_0_label)s` |
  | `uq` (unique) | `uq_%(table_name)s_%(column_0_name)s` |
  | `ck` (check) | `ck_%(table_name)s_%(constraint_name)s` |
  | `fk` (foreign key) | `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s` |
  | `pk` (primary key) | `pk_%(table_name)s` |

#### Example table: `pings`

The only table created by this spec, purely to prove the migration workflow.

| Column | Type | Constraints / notes |
| --- | --- | --- |
| `id` | `UUID` | PK, default `uuid4()` (app-side), not null |
| `note` | `VARCHAR(200)` | not null, default `''` |
| `created_at` | `TIMESTAMPTZ` | not null, default `now()` |
| `updated_at` | `TIMESTAMPTZ` | not null, default `now()`, `onupdate now()` |

- Mapped with SQLAlchemy 2.0 typed `Mapped[...]` / `mapped_column(...)` style.
- Model class `Ping(UUIDPrimaryKeyMixin, TimestampMixin, Base)` in
  `backend/src/inkstave/db/models/ping.py` (or `models.py` if a single file is
  cleaner — keep the directory ready for feature models).

#### Migration expectations

- Alembic `versions/` contains exactly **one** migration after this spec: the
  initial migration creating `pings` (and enabling any required extension if you
  choose server-side UUIDs — but the app-side default avoids this).
- `alembic upgrade head` creates the table; `alembic downgrade base` drops it.
- Running `alembic revision --autogenerate` against an up-to-date DB produces an
  **empty** migration (proving metadata and DB agree).

### 5.2 Backend / API (if any)

#### Module layout (under `backend/src/inkstave/db/`)

```
db/
├── __init__.py
├── base.py             # MetaData(naming_convention=...), Base, mixins
├── engine.py           # create_engine_and_sessionmaker(settings) -> (engine, sessionmaker)
├── session.py          # get_db_session() FastAPI dependency
└── models/
    ├── __init__.py     # imports all models so Alembic sees them
    └── ping.py         # Ping example model
```

Plus Alembic at `backend/`:

```
backend/
├── alembic.ini
└── migrations/
    ├── env.py          # async env, target_metadata=Base.metadata, DSN from settings
    ├── script.py.mako
    └── versions/
        └── <rev>_create_pings.py
```

#### Engine & session (`engine.py`, `session.py`)

- `create_async_engine(settings.database_url, echo=settings.debug,
  pool_pre_ping=True)`. Ensure the DSN uses the `postgresql+asyncpg://` driver;
  if a bare `postgresql://` is provided, normalize it.
- `async_sessionmaker(engine, expire_on_commit=False, autoflush=False)`.
- Engine + sessionmaker are created in the **lifespan** (extending spec 02's
  lifespan) and stored on `app.state.db_engine` / `app.state.db_sessionmaker`;
  the engine is `await engine.dispose()`d on shutdown.
- `get_db_session()` dependency:
  - Acquires a session from `app.state.db_sessionmaker`.
  - `yield`s it inside a `try/except/finally`.
  - On normal completion: `await session.commit()`.
  - On exception: `await session.rollback()` then re-raise.
  - Always: `await session.close()`.
  - One transaction per request. (Features needing finer control can manage
    nested transactions/savepoints themselves.)

#### Base & mixins (`base.py`)

- `metadata = MetaData(naming_convention=NAMING_CONVENTION)`.
- `class Base(DeclarativeBase): metadata = metadata`.
- `UUIDPrimaryKeyMixin`: `id: Mapped[uuid.UUID] = mapped_column(primary_key=
  True, default=uuid.uuid4)`.
- `TimestampMixin`: `created_at`, `updated_at` as `Mapped[datetime]` with
  `server_default=func.now()` and `onupdate=func.now()`; both timezone-aware.

#### Alembic `env.py` (async)

- Imports `Base` and all models (via `db.models.__init__`) so autogenerate sees
  every table.
- `target_metadata = Base.metadata`.
- Reads the DSN from `get_settings().database_url` (not hard-coded in
  `alembic.ini`), normalizing to the async driver.
- Offline mode: emit SQL using the DSN.
- Online mode: use `async_engine_from_config` / `create_async_engine` and run
  migrations via `connection.run_sync(do_run_migrations)` inside
  `asyncio.run(...)`.
- `compare_type=True` and `compare_server_default=True` for accurate
  autogenerate.

#### Readiness extension

- Extend `/ready` (spec 02) to add a `db` check: acquire a connection and run
  `SELECT 1` with a short timeout; on success `checks.db = "ok"`, on failure
  `checks.db = "error"` and overall `503`. The Redis check from spec 02 stays.

### 5.3 Frontend / UI (if any)

None.

### 5.4 Real-time / jobs / external integrations (if any)

None. (No jobs read/write the DB yet; ARQ arrives in spec 22.)

### 5.5 Configuration

- New runtime deps in `backend/pyproject.toml`: `sqlalchemy[asyncio]>=2`,
  `asyncpg`, `alembic`. Add the SQLAlchemy mypy plugin to `[tool.mypy]` if used.
- `.env.example`: `DATABASE_URL` already exists (spec 01). Add an optional
  `DB_ECHO` (`false`) if you expose SQL echo separately from `DEBUG`
  (otherwise reuse `DEBUG`). Document whichever you choose.
- `alembic.ini`: present at `backend/alembic.ini`; `script_location =
  migrations`; logging section consistent with the app's logging (Alembic's own
  loggers are fine).
- `justfile` additions:
  - `just migrate` → `uv run alembic -c backend/alembic.ini upgrade head`.
  - `just makemigration name="..."` → `uv run alembic -c backend/alembic.ini
    revision --autogenerate -m "{{name}}"`.
  - `just downgrade` → `uv run alembic -c backend/alembic.ini downgrade -1`.

## 6. Overleaf reference (study only — never copy)

> Overleaf's main `web` service uses **MongoDB/Mongoose**, not SQL — so it is a
> reference for *model/schema organization*, not for SQLAlchemy itself. The
> `history-v1` service genuinely uses **Postgres + Knex migrations** and is the
> better reference for migration discipline. Inkstave code is independent.

- `services/web/app/src/models/` — verified present (e.g. `Project.mjs`,
  `Doc.mjs`, `Folder.mjs`, `File.mjs`, `User.mjs`). Study how models are
  organized one-per-file and registered. Inkstave mirrors the *organization*
  with SQLAlchemy models under `db/models/`, but the schemas differ (SQL vs
  document).
- `services/web/app/src/infrastructure/Mongoose.mjs` — verified present. Study
  how the single DB connection/registration is centralized. Inkstave centralizes
  the async engine/sessionmaker in `db/engine.py` + lifespan instead.
- `services/history-v1/knexfile.js` — verified present. Study how a real
  Postgres service configures its migration tool and connection. Inkstave uses
  Alembic; take the *discipline* (versioned, ordered, reversible migrations).
- `services/history-v1/migrations/` — verified present (timestamped migration
  files like `20220228163642_initial.js`). Study migration naming/ordering and
  that each migration is append-only and reversible. Inkstave's Alembic
  `versions/` follows the same discipline (never edit a released migration; add
  a new one).
- `services/history-v1/storage/lib/knex.js` — verified present. Study how the
  Knex client is created/shared. Inkstave's analogue is `db/engine.py`.

No Overleaf equivalent exists for: SQLAlchemy 2.x async sessions, Alembic
async `env.py`, or the SQLAlchemy naming-convention metadata — design those from
the SQLAlchemy/Alembic docs.

## 7. Acceptance criteria

1. **Given** the app starts, **when** the lifespan runs, **then** an async
   engine and sessionmaker are created and stored on `app.state`; on shutdown
   the engine is disposed (verifiable via a spy/log).
2. **Given** `get_db_session()`, **when** a request handler completes
   successfully, **then** the session is committed and closed exactly once.
3. **Given** `get_db_session()`, **when** the handler raises, **then** the
   session is rolled back (no partial write persists) and then closed, and the
   exception propagates.
4. **Given** a clean database, **when** I run `alembic upgrade head`, **then**
   the `pings` table exists with columns `id, note, created_at, updated_at` and
   a primary key named `pk_pings`.
5. **Given** `head` applied, **when** I run `alembic downgrade base`, **then**
   the `pings` table is dropped without error.
6. **Given** the DB is at `head` and matches the models, **when** I run
   `alembic revision --autogenerate`, **then** the generated migration's
   `upgrade()`/`downgrade()` bodies are empty (metadata == DB).
7. **Given** a `Ping(note="hi")` inserted and committed, **when** I query it
   back, **then** `id` is a UUID, `created_at` and `updated_at` are set and
   timezone-aware, and updating `note` bumps `updated_at`.
8. **Given** the naming convention, **when** any constraint is created (e.g. a
   unique constraint in a later test), **then** its name follows the registered
   templates (e.g. `uq_<table>_<col>`).
9. **Given** the DB reachable, **when** I `GET /ready`, **then** `checks.db ==
   "ok"` (and `checks.redis` per spec 02); **given** the DB unreachable, **then**
   `checks.db == "error"` and the response is `503` within the timeout.
10. **Given** a bare `postgresql://...` DSN, **when** the engine is created,
    **then** it is normalized to the `postgresql+asyncpg://` driver.

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> DB tests run against an ephemeral Postgres using transactions; no slow work.

- **Unit (pytest):**
  - DSN normalization (`postgresql://` → `postgresql+asyncpg://`).
  - `TimestampMixin`/`UUIDPrimaryKeyMixin` produce the expected column defaults
    (inspect the mapper/columns).
  - Naming convention is registered on `Base.metadata`.
- **Integration (pytest + async session against a real ephemeral Postgres):**
  - Create schema (via `Base.metadata.create_all` *or* by running migrations —
    prefer running the Alembic migration once to also exercise it), insert and
    read a `Ping`, assert UUID + timestamps + `updated_at` bump.
  - `get_db_session()` commit-on-success and rollback-on-error behavior using a
    tiny test-only route.
  - `/ready` returns `checks.db == "ok"` with a live DB; returns `error`/`503`
    when the DB check is forced to fail (inject a failing connection/timeout).
  - Migration round-trip: `upgrade head` then `downgrade base` then `upgrade
    head` again succeeds (can run via Alembic's API in-process against the test
    DB).
  - Autogenerate produces an empty diff when DB == metadata.
  - **Test DB provisioning here is minimal/local to this spec** (e.g. a
    throwaway database created/dropped around the module, or the developer's
    compose Postgres pointed at a `*_test` database). The *reusable*, fast
    fixture strategy (template DB / transactional rollback per test) is
    delivered in **spec 04**, which these tests will later adopt.
- **E2E (Playwright):** not applicable (no UI).
- **Performance/budget note:** DB tests must use a **local/ephemeral** Postgres
  (the compose service or a CI service container), wrap work in transactions and
  roll back, and avoid per-test full-schema recreation where possible. No real
  LaTeX/LLM. Keep this spec's DB tests to a handful so total time is a couple of
  seconds; spec 04 then optimizes provisioning for the whole suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented (async engine/session, Base + mixins,
      naming convention, session dependency with transaction semantics, async
      Alembic with autogenerate, `pings` table + initial migration, `/ready` DB
      check).
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] `ruff`/`mypy` clean; `alembic upgrade head`/`downgrade base` both work.
- [ ] New env vars (if any) documented in `.env.example`; ADR for migration
      workflow + naming conventions added under `docs/`.
- [ ] No Overleaf code copied.
