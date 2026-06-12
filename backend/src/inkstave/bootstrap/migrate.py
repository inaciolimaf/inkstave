"""Advisory-locked, run-once Alembic migration runner (spec 57).

When ``backend``, ``worker`` and ``collab`` start together, only the holder of a
fixed Postgres **advisory lock** runs ``alembic upgrade head``; the others block,
then re-run the upgrade as a no-op (migrations are forward-only and idempotent).
The lock is taken on a dedicated sync (psycopg2) connection so it spans the whole
upgrade, which Alembic runs on its own async connection (env.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from inkstave.config import Settings
from inkstave.db.engine import normalize_async_dsn

logger = logging.getLogger("inkstave.migrate")

# alembic.ini sits at the project root next to migrations/ — in the container that
# is /app/alembic.ini (WORKDIR /app); in the repo it is backend/alembic.ini.
_DEFAULT_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"

# A fixed key so every process contends for the *same* migration lock.
MIGRATION_LOCK_KEY = 0x494E4B53  # "INKS"


def _alembic_config(ini: Path | None = None) -> Config:
    return Config(str(ini or _DEFAULT_ALEMBIC_INI))


def _sync_dsn(database_url: str) -> str:
    """A psycopg2 (sync) DSN for the advisory-lock connection."""
    return normalize_async_dsn(database_url).replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )


def script_head(ini: Path | None = None) -> str | None:
    """The latest revision id defined by the migration scripts."""
    return ScriptDirectory.from_config(_alembic_config(ini)).get_current_head()


def acquire_advisory_lock(conn: Connection, key: int = MIGRATION_LOCK_KEY) -> None:
    conn.exec_driver_sql("SELECT pg_advisory_lock(%(k)s)", {"k": key})


def release_advisory_lock(conn: Connection, key: int = MIGRATION_LOCK_KEY) -> None:
    conn.exec_driver_sql("SELECT pg_advisory_unlock(%(k)s)", {"k": key})


def run_upgrade(
    settings: Settings, *, ini: Path | None = None, lock_key: int = MIGRATION_LOCK_KEY
) -> None:
    """Upgrade the database to head under the advisory lock (run-once safe).

    Synchronous on purpose: Alembic's env.py runs its own ``asyncio.run``, so this
    must NOT be called from a running event loop — call it via
    ``asyncio.to_thread`` from async code.
    """
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    engine = create_engine(_sync_dsn(settings.database_url), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            acquire_advisory_lock(conn, lock_key)
            try:
                logger.info("Applying database migrations to head")
                command.upgrade(_alembic_config(ini), "head")
            finally:
                release_advisory_lock(conn, lock_key)
    finally:
        engine.dispose()


async def current_revision(engine: AsyncEngine) -> str | None:
    """The DB's current Alembic revision, or ``None`` if never migrated."""
    async with engine.connect() as conn:
        try:
            result = await conn.exec_driver_sql("SELECT version_num FROM alembic_version")
            return result.scalar()
        except Exception:
            return None  # alembic_version table absent


async def is_database_at_head(engine: AsyncEngine, *, ini: Path | None = None) -> bool:
    """True if the DB is migrated to the latest script revision."""
    return await current_revision(engine) == script_head(ini)
