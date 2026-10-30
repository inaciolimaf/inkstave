"""Every application connection has a deadline, and the known long waits survive it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from inkstave.core.config.settings import Settings
from inkstave.core.db.engine import create_engine_and_sessionmaker
from inkstave.core.db.session import allow_idle, allow_long_statements

pytestmark = pytest.mark.integration


async def _show(session: AsyncSession, name: str) -> str:
    result = await session.connection()
    return (await result.exec_driver_sql(f"SHOW {name}")).scalar_one()


def _settings(db_engine: Any, **overrides: Any) -> Settings:
    url = db_engine.url.render_as_string(hide_password=False)
    return Settings(_env_file=None, database_url=url, **overrides)  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def quick_limits(db_engine: Any) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    settings = _settings(db_engine, db_idle_in_transaction_timeout_s=1, db_statement_timeout_s=1)
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    yield sessionmaker
    await engine.dispose()


async def test_defaults_are_set_on_a_real_connection(db_engine: Any) -> None:
    engine, sessionmaker = create_engine_and_sessionmaker(_settings(db_engine))
    try:
        async with sessionmaker() as session:
            assert await _show(session, "lock_timeout") == "10s"
            assert await _show(session, "statement_timeout") == "30s"
            assert await _show(session, "idle_in_transaction_session_timeout") == "2min"
    finally:
        await engine.dispose()


async def test_an_idle_transaction_past_the_limit_is_killed(
    quick_limits: async_sessionmaker[AsyncSession],
) -> None:
    async with quick_limits() as session:
        await session.execute(select(1))
        await asyncio.sleep(1.3)
        with pytest.raises(DBAPIError):
            await session.execute(select(1))


async def test_allow_idle_survives_the_wait_and_ends_with_the_transaction(
    quick_limits: async_sessionmaker[AsyncSession],
) -> None:
    async with quick_limits() as session:
        await allow_idle(session, 5)
        await asyncio.sleep(1.3)
        await session.execute(select(1))
        await session.commit()
        assert await _show(session, "idle_in_transaction_session_timeout") == "1s"


async def test_allow_long_statements_only_lasts_for_the_transaction(
    quick_limits: async_sessionmaker[AsyncSession],
) -> None:
    async with quick_limits() as session:
        await allow_long_statements(session)
        assert await _show(session, "statement_timeout") == "5min"
        await session.commit()
        assert await _show(session, "statement_timeout") == "1s"
