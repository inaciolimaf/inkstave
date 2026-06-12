# ADR 0003 — Database foundation: migrations, naming, identifiers, sessions

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 03 — Database Foundation

## Context

Spec 03 wires PostgreSQL into the app via async SQLAlchemy 2.x and Alembic.
Several conventions established here are inherited by every future table and
feature, so they are recorded once.

## Decisions

### 1. Migration tool & discipline: Alembic, async, autogenerate

- **Alembic** is the single migration tool, configured for **async**
  (`create_async_engine` + `connection.run_sync` inside `asyncio.run`).
- `env.py` reads the DSN from **application settings** (`DATABASE_URL`),
  normalized to the `postgresql+asyncpg://` driver — never hard-coded in
  `alembic.ini` — so app and migrations always target the same database.
- `target_metadata = Base.metadata` with `db.models` imported, and
  `compare_type=True` / `compare_server_default=True`, so `--autogenerate`
  diffs are accurate.
- **Discipline:** migrations are versioned, ordered and reversible. A released
  migration is **never edited**; changes ship as new migrations. Timestamped
  filenames (`file_template`) keep ordering obvious.

### 2. Constraint naming convention on the shared metadata

A single `MetaData(naming_convention=...)` gives every constraint a
deterministic name, which keeps autogenerate diffs stable and makes
constraints referenceable in later migrations:

| Type | Template |
| --- | --- |
| `ix` | `ix_%(column_0_label)s` |
| `uq` | `uq_%(table_name)s_%(column_0_name)s` |
| `ck` | `ck_%(table_name)s_%(constraint_name)s` |
| `fk` | `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s` |
| `pk` | `pk_%(table_name)s` |

### 3. Primary keys: app-side UUID v4

All tables use a UUID `id` defaulted **app-side** (`default=uuid.uuid4`) rather
than a server default (`gen_random_uuid()`), to avoid depending on the
`pgcrypto`/`uuid-ossp` extension and to keep ids available before flush. The
trade-off (ids generated in Python, not the DB) is acceptable and uniform.

### 4. Timestamps

`created_at` / `updated_at` are `TIMESTAMP WITH TIME ZONE`, both
`server_default=now()`; `updated_at` additionally carries `onupdate=now()` so
the database stamps modifications. Timezone-aware throughout.

### 5. Session strategy: one transaction per request

`get_db_session()` yields one `AsyncSession` per request from an
`async_sessionmaker(expire_on_commit=False, autoflush=False)`: **commit** on
success, **rollback** on exception, **close** always. This is the default;
features that need finer control open nested transactions/savepoints on the
yielded session. The engine + sessionmaker are created once in the app
lifespan (beside Redis) and disposed on shutdown.

### 6. SQL echo follows `DEBUG`

Rather than add a separate `DB_ECHO` setting, the engine's `echo` reuses the
existing `DEBUG` flag — one knob for verbose local diagnostics. A dedicated
`DB_ECHO` can be introduced later via a new ADR if independent control is
needed.

## Consequences

- New runtime deps: `sqlalchemy[asyncio]>=2`, `asyncpg`, `alembic`.
- `/ready` now checks the database (`SELECT 1`, short timeout) in addition to
  Redis; both must pass for `200`.
- Exactly one migration exists after this spec (`create pings`); the `pings`
  table is a throwaway proving the workflow and will coexist with real models.
- New `justfile` recipes: `migrate`, `makemigration name="…"`, `downgrade`.
- DB tests provision a throwaway `*_test` database locally; the reusable,
  optimized fixture strategy is delivered in spec 04.

## Alternatives considered

- **Server-side UUID default (`gen_random_uuid()`)** — requires a DB extension
  and hides id generation from the app; rejected for app-side `uuid4()`.
- **`created`/`updated` as naive timestamps** — rejected; timezone-aware avoids
  ambiguity.
- **Repository/unit-of-work abstraction now** — out of scope; the session
  dependency suffices, and features may add patterns later.
- **A separate `DB_ECHO` flag** — unnecessary indirection today; reuse `DEBUG`.
