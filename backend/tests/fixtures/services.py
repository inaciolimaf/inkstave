"""Redis fake, wired app and ASGI client fixtures (spec 04).

Registered as a pytest plugin from the root ``tests/conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.app import create_app
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_redis

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
