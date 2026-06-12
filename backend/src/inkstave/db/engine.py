"""Async engine + session factory and database readiness helpers.

The engine and ``async_sessionmaker`` are created once in the app lifespan and
shared via ``app.state``; request code reaches a session through
:func:`inkstave.db.session.get_db_session`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from inkstave.config import Settings


def normalize_async_dsn(url: str) -> str:
    """Ensure ``url`` uses the ``postgresql+asyncpg://`` async driver."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url


def create_engine_and_sessionmaker(
    settings: Settings,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build the async engine and session factory from settings.

    Raises ``ValueError`` if ``database_url`` is not configured.
    """
    if not settings.database_url:
        raise ValueError("database_url is not configured")
    engine = create_async_engine(
        normalize_async_dsn(settings.database_url),
        echo=settings.debug,
        pool_pre_ping=True,
    )
    sessionmaker = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
    return engine, sessionmaker


async def check_db(engine: AsyncEngine, timeout_seconds: float) -> bool:
    """Run ``SELECT 1`` against the database; return ``False`` on any failure."""
    try:
        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
