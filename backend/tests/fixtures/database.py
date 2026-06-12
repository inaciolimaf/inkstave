"""Test-database fixtures: provision + migrate ONCE, roll back per test (spec 04).

Registered as a pytest plugin from the root ``tests/conftest.py``.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.fixtures.paths import ALEMBIC_INI

# --------------------------------------------------------------------------- #
# Test database: provision + migrate ONCE (template), rollback per test
# --------------------------------------------------------------------------- #


async def _admin_exec(admin_url: Any, statements: list[str]) -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=admin_url.host,
        port=admin_url.port,
        user=admin_url.username,
        password=admin_url.password,
        database=admin_url.database,
    )
    try:
        for stmt in statements:
            await conn.execute(stmt)
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def _template_db() -> Iterator[str]:
    """Create the test database and migrate it to head exactly once.

    Spec 53 AC2 literally reads "each xdist worker uses its own DB cloned from a
    once-migrated template, migrations run once". Here, under xdist, each worker
    fixture runs ``command.upgrade(..., 'head')`` against its own worker DB, so
    migrations run once *per worker* rather than once globally. This deviation is
    knowingly accepted per ADR-0053: a true ``CREATE DATABASE ... TEMPLATE`` clone
    would require cross-worker coordination (a single migrating worker the others
    block on) for marginal wall-clock gain on a fast migration set; per-worker
    migration is simpler, fully isolated, and keeps the suite well under budget.
    """
    url = make_url(os.environ["DATABASE_URL"])
    db_name = url.database or "inkstave_test"
    admin_url = url.set(drivername="postgresql", database="postgres")
    test_url = url.render_as_string(hide_password=False)

    try:
        asyncio.run(
            _admin_exec(
                admin_url,
                [
                    f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)',
                    f'CREATE DATABASE "{db_name}"',
                ],
            )
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not available for the test database: {exc}")

    # Build the schema template ONCE for the whole session.
    command.upgrade(Config(str(ALEMBIC_INI)), "head")

    yield test_url

    asyncio.run(_admin_exec(admin_url, [f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)']))


@pytest_asyncio.fixture
async def db_engine(_template_db: str) -> AsyncIterator[Any]:
    """A function-scoped engine bound to the current test's event loop."""
    engine = create_async_engine(_template_db)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def query_counter(db_engine: Any) -> AsyncIterator[dict[str, int]]:
    """Count SELECT/INSERT/UPDATE/DELETE statements on the test engine.

    Used by perf-sanity tests to prove hot paths issue no N+1 queries (the
    statement count must not scale with the number of rows).
    """
    from sqlalchemy import event

    counter = {"count": 0}

    def _on_exec(_conn: Any, _cursor: Any, statement: str, *_args: Any, **_kwargs: Any) -> None:
        if statement.lstrip()[:6].upper() in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            counter["count"] += 1

    event.listen(db_engine.sync_engine, "before_cursor_execute", _on_exec)
    try:
        yield counter
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _on_exec)


@pytest_asyncio.fixture
async def db_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    """A session inside an outer transaction that is rolled back after the test.

    ``join_transaction_mode="create_savepoint"`` lets endpoint/test code call
    ``commit()`` (which releases a SAVEPOINT) while the outer transaction is
    discarded on teardown — full isolation without rebuilding the schema.
    """
    connection = await db_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
