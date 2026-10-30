"""The unit of work: one session per request, committed before the response leaves.

Reach it as ``session: AsyncSession = UNIT_OF_WORK``, never with a bare
``Depends(get_db_session)``. FastAPI's default scope runs the code after ``yield`` once the
response has been sent, so a failed commit would reach the client as a 200 with nothing saved.
``scope="function"`` closes the session first, which turns that failure into a 500. A repeated
``Depends`` with another scope would also open a second session, hence the single constant.

A response body that streams after the route returns has no session: it must read what it needs
first, or open a short one from :func:`get_session_factory`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inkstave.core.deps import ServiceUnavailableError

LONG_STATEMENT_SECONDS = 300


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "db_sessionmaker", None
    )
    if sessionmaker is None:
        raise ServiceUnavailableError("Database is not available")
    return sessionmaker


async def get_db_session(
    factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session with commit/rollback/close semantics."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


UNIT_OF_WORK = Depends(get_db_session, scope="function")


async def allow_idle(session: AsyncSession, seconds: int) -> None:
    """Raise the idle limit for this transaction, before a wait that cannot happen outside one."""
    await session.execute(select(func.set_config("idle_in_transaction_session_timeout", f"{seconds}s", True)))


async def allow_long_statements(session: AsyncSession, seconds: int = LONG_STATEMENT_SECONDS) -> None:
    """Raise the statement limit for this transaction, for a known heavy statement."""
    await session.execute(select(func.set_config("statement_timeout", f"{seconds}s", True)))
