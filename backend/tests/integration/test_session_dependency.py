"""Integration tests driving the real ``get_db_session`` dependency.

These cover the actual commit/rollback/close path (the test ``app`` fixture
overrides ``get_db_session`` with a copy, so the real one needs its own
coverage). A session-maker bound to a transactional connection keeps the rows
isolated and rolled back.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from inkstave.db.models.ping import Ping
from inkstave.db.session import get_db_session

pytestmark = pytest.mark.integration


async def _count(sessionmaker: Any, note: str) -> int:
    async with sessionmaker() as session:
        stmt = select(func.count()).select_from(Ping).where(Ping.note == note)
        return int((await session.execute(stmt)).scalar_one())


async def test_get_db_session_commits_on_success(db_engine: Any) -> None:
    connection = await db_engine.connect()
    outer = await connection.begin()
    sessionmaker = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_sessionmaker=sessionmaker))
    )
    try:
        gen = get_db_session(request)  # type: ignore[arg-type]
        session = await anext(gen)
        session.add(Ping(note="dep-commit"))
        with pytest.raises(StopAsyncIteration):
            await anext(gen)  # resume past yield -> commit + close
        assert await _count(sessionmaker, "dep-commit") == 1
    finally:
        await outer.rollback()
        await connection.close()


async def test_get_db_session_rolls_back_on_error(db_engine: Any) -> None:
    connection = await db_engine.connect()
    outer = await connection.begin()
    sessionmaker = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_sessionmaker=sessionmaker))
    )
    try:
        gen = get_db_session(request)  # type: ignore[arg-type]
        session = await anext(gen)
        session.add(Ping(note="dep-rollback"))
        await session.flush()
        with pytest.raises(RuntimeError):
            await gen.athrow(RuntimeError("boom"))  # -> except: rollback + re-raise
        assert await _count(sessionmaker, "dep-rollback") == 0
    finally:
        await outer.rollback()
        await connection.close()
