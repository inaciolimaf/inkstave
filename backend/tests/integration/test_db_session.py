"""Integration tests for the transactional session fixture and factories.

These prove (a) the session dependency's commit/rollback semantics through a
wired endpoint, and (b) that the rollback-per-test strategy isolates state.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.ping import Ping
from inkstave.db.session import get_db_session
from tests.factories import PingFactory

pytestmark = pytest.mark.integration


async def _count_pings(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Ping))).scalar_one())


async def test_endpoint_commit_is_visible(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    async def insert(note: str, session: AsyncSession = Depends(get_db_session)) -> dict[str, bool]:
        session.add(Ping(note=note))
        return {"ok": True}

    app.add_api_route("/_t/insert", insert, methods=["POST"])
    resp = await async_client.post("/_t/insert", params={"note": "committed"})
    assert resp.status_code == 200
    assert await _count_pings(db_session) == 1


async def test_endpoint_error_rolls_back(
    app: Any, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    async def insert_then_fail(
        note: str, session: AsyncSession = Depends(get_db_session)
    ) -> dict[str, bool]:
        session.add(Ping(note=note))
        raise RuntimeError("boom after add")

    app.add_api_route("/_t/fail", insert_then_fail, methods=["POST"])
    resp = await async_client.post("/_t/fail", params={"note": "rolled"})
    assert resp.status_code == 500
    assert await _count_pings(db_session) == 0


async def test_factory_creates_distinct_persisted_pings(db_session: AsyncSession) -> None:
    first = await PingFactory.create(db_session)
    second = await PingFactory.create(db_session)
    assert isinstance(first.id, uuid.UUID)
    assert first.id != second.id
    assert first.note != second.note
    assert await _count_pings(db_session) == 2


async def test_rollback_isolation(db_session: AsyncSession) -> None:
    # Despite the previous test creating pings, this test starts empty —
    # proving each test runs in its own rolled-back transaction.
    assert await _count_pings(db_session) == 0
