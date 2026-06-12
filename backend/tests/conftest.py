"""Shared test fixtures and harness — the testing foundation (spec 04).

Design goals (see docs/adr/0004-testing-foundation.md):

* **Fast.** ASGI-transport client (no sockets), a faked Redis, and a test
  database migrated **once per session** into a template, with each test wrapped
  in a transaction that is **rolled back** (no per-test schema rebuild, no
  cross-test state).
* **By convention.** Feature specs reuse these fixtures (`async_client`,
  `db_session`, `redis`, `settings_override`, `app`) and add factories under
  ``tests/factories/``.
* **No slow externals.** Tectonic and the LLM are never invoked; slow work lives
  in ARQ jobs whose bodies are mocked.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from inkstave.app import create_app
from inkstave.config import Settings, get_settings
from inkstave.db.engine import normalize_async_dsn
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_redis
from inkstave.logging import set_request_id

_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

_DEFAULT_TEST_DB = "postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave_test"


# --------------------------------------------------------------------------- #
# Environment / settings
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session", autouse=True)
def _configure_test_env() -> Iterator[None]:
    """Force test settings for the whole session.

    Points the app and Alembic at ``TEST_DATABASE_URL`` and selects readable,
    non-JSON logs. Individual unit tests may still construct ``Settings`` with
    explicit overrides (``_env_file=None`` + monkeypatched env).
    """
    test_db_url = normalize_async_dsn(os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB))
    overrides = {
        "DATABASE_URL": test_db_url,
        "ENVIRONMENT": "test",
        "LOG_JSON": "false",
        # Minimal argon2 cost so password hashing is sub-millisecond in tests.
        "ARGON2_TIME_COST": "1",
        "ARGON2_MEMORY_COST": "8",
        "ARGON2_PARALLELISM": "1",
        # Deterministic JWT signing secret for tests (spec 07).
        "JWT_SECRET": "test-secret-not-for-production-0123456789abcdef",
        # High rate limits by default (spec 08); the 429 test overrides these.
        "RATE_LIMIT_LOGIN": "1000/300",
        "RATE_LIMIT_REGISTER": "1000/3600",
        "RATE_LIMIT_REFRESH": "1000/300",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_request_state() -> Iterator[None]:
    """Clear cached settings + request-id context around every test."""
    get_settings.cache_clear()
    set_request_id(None)
    yield
    get_settings.cache_clear()
    set_request_id(None)


@pytest.fixture
def settings_override() -> Settings:
    """The active test :class:`Settings` (environment=test, JSON logs off)."""
    return get_settings()


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
    """Create the test database and migrate it to head exactly once."""
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
    command.upgrade(Config(str(_ALEMBIC_INI)), "head")

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


# --------------------------------------------------------------------------- #
# Redis fake
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Any]:
    """A faked async Redis (no real Redis process); flushed after each test."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


# --------------------------------------------------------------------------- #
# Wired app + client
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def app(db_engine: Any, db_session: AsyncSession, redis: Any) -> Any:
    """``create_app()`` wired for tests: fake Redis + transactional DB session.

    ``app.state`` carries the fake Redis and the real test engine (so the
    state-reading ``/ready`` probe works), while the ``get_db_session`` and
    ``get_redis`` dependencies are overridden so endpoint writes share the
    rolled-back transaction.
    """
    application = create_app()
    application.state.redis = redis
    application.state.db_engine = db_engine

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        # Mirror the real commit/rollback semantics but leave close to the
        # db_session fixture, which owns the outer transaction.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    application.dependency_overrides[get_db_session] = _override_get_db
    application.dependency_overrides[get_redis] = lambda: redis
    return application


@pytest_asyncio.fixture
async def async_client(app: Any) -> AsyncIterator[AsyncClient]:
    """ASGI-transport client (no sockets) bound to the wired test app."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# --------------------------------------------------------------------------- #
# Fakes for failure-mode injection (used by readiness tests)
# --------------------------------------------------------------------------- #


class FakeRedisRaising:
    """Stub Redis whose ping raises (simulates an unreachable server)."""

    async def ping(self) -> bool:
        raise ConnectionError("redis down")


class FakeRedisHanging:
    """Stub Redis whose ping hangs past any sane timeout."""

    async def ping(self) -> bool:
        await asyncio.sleep(5)
        return True


class _FakeConnection:
    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def execute(self, *_args: object) -> None:
        return None


class FakeEngineOk:
    """Stub async engine whose ``SELECT 1`` succeeds (no real DB)."""

    def connect(self) -> _FakeConnection:
        return _FakeConnection()


class FakeEngineBroken:
    """Stub async engine whose connection attempt fails immediately."""

    def connect(self) -> _FakeConnection:
        raise OSError("database unreachable")
