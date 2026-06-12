"""Reset the e2e test database to a clean, migrated state (spec 54).

Drops and recreates the database named in ``DATABASE_URL`` (with FORCE so open
connections don't block it), then runs Alembic to ``head``. The Playwright
backend ``webServer`` runs this before Uvicorn so every ``playwright test`` run
starts from an empty schema — deterministic, no cross-run state.

Usage:  python scripts/e2e_reset_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


async def _admin_exec(admin_url: object, statements: list[str]) -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=admin_url.host,  # type: ignore[attr-defined]
        port=admin_url.port,  # type: ignore[attr-defined]
        user=admin_url.username,  # type: ignore[attr-defined]
        password=admin_url.password,  # type: ignore[attr-defined]
        database=admin_url.database,  # type: ignore[attr-defined]
    )
    try:
        for stmt in statements:
            await conn.execute(stmt)
    finally:
        await conn.close()


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    url = make_url(dsn)
    db_name = url.database or "inkstave_e2e"
    admin_url = url.set(drivername="postgresql", database="postgres")

    asyncio.run(
        _admin_exec(
            admin_url,
            [
                f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)',
                f'CREATE DATABASE "{db_name}"',
            ],
        )
    )
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")
    print(f"e2e database '{db_name}' reset and migrated to head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
