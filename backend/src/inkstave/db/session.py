"""The transaction-scoped FastAPI database session dependency.

``get_db_session`` yields one :class:`AsyncSession` per request: it commits on
success, rolls back on exception, and always closes. Features needing finer
control can open nested transactions/savepoints on the yielded session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inkstave.dependencies import ServiceUnavailableError


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session with commit/rollback/close semantics."""
    sessionmaker: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "db_sessionmaker", None
    )
    if sessionmaker is None:
        raise ServiceUnavailableError("Database is not available")

    session = sessionmaker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
