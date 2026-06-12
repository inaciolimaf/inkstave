"""Integration perf tests: cache, N+1 query bounds, DB pool (spec 53)."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.tokens import build_token_service
from inkstave.cache import project_meta_key
from inkstave.config import get_settings
from inkstave.db.engine import create_engine_and_sessionmaker
from inkstave.db.models.history import HistoryChunk, HistoryUpdate
from inkstave.db.models.membership import (
    MembershipRole,
    MembershipStatus,
    ProjectMembership,
)
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.history.read import list_versions
from inkstave.services import sharing, tree_service
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _auth(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


# --- hot-read cache: hit + invalidation (AC7) ------------------------------- #


async def test_project_metadata_cache_hit_and_invalidation(
    async_client: AsyncClient, db_session: AsyncSession, redis: Any
) -> None:
    headers = await _auth(db_session)
    created = await async_client.post("/api/v1/projects", json={"name": "Orig"}, headers=headers)
    pid = created.json()["id"]
    key = project_meta_key(pid)

    assert await redis.get(key) is None
    first = await async_client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert first.json()["name"] == "Orig"
    assert await redis.get(key) is not None  # populated → served from Redis next time

    # A write invalidates the cache so the next read reflects the change.
    await async_client.patch(f"/api/v1/projects/{pid}", json={"name": "Renamed"}, headers=headers)
    assert await redis.get(key) is None
    after = await async_client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert after.json()["name"] == "Renamed"


async def test_cache_helper_disabled_mode_bypasses(redis: Any) -> None:
    from types import SimpleNamespace

    from inkstave.cache import RedisCache

    cache = RedisCache(redis, SimpleNamespace(cache_enabled=False, cache_ttl_seconds=30))
    await cache.set_json("k", {"a": 1})
    assert await cache.get_json("k") is None  # disabled → never reads/writes Redis
    assert await redis.get("k") is None


# --- N+1 query bound (AC6) -------------------------------------------------- #


async def test_file_tree_query_count_is_bounded(
    db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    user = await UserFactory.create(db_session)
    project = await create_project(db_session, user.id, "P")
    for i in range(5):
        await create_entity(db_session, project.id, TreeEntityType.doc, f"a{i}.tex", None)
    await db_session.flush()

    query_counter["count"] = 0
    tree_service.build_tree(await tree_service.get_tree(db_session, project.id))
    with_five = query_counter["count"]

    for i in range(25):
        await create_entity(db_session, project.id, TreeEntityType.doc, f"b{i}.tex", None)
    await db_session.flush()

    query_counter["count"] = 0
    tree_service.build_tree(await tree_service.get_tree(db_session, project.id))
    with_thirty = query_counter["count"]

    assert with_five == with_thirty  # query count does not scale with rows — no N+1
    assert with_thirty <= 3


async def _seed_history(
    db_session: AsyncSession,
    project_id: Any,
    doc_id: Any,
    author_id: Any,
    *,
    start: int,
    count: int,
) -> None:
    """Append a sealed chunk with ``count`` update rows starting at version ``start``."""
    from datetime import UTC, datetime

    end = start + count - 1
    chunk = HistoryChunk(
        project_id=project_id,
        doc_id=doc_id,
        start_version=start,
        end_version=end,
        base_version=start - 1,
        base_snapshot=b"",
        base_snapshot_size=0,
        sealed=True,  # avoid the at-most-one-open-chunk unique index
    )
    db_session.add(chunk)
    await db_session.flush()
    now = datetime(2026, 6, 10, tzinfo=UTC)
    for version in range(start, end + 1):
        db_session.add(
            HistoryUpdate(
                chunk_id=chunk.id,
                project_id=project_id,
                doc_id=doc_id,
                version=version,
                timestamp=now,
                author_id=author_id,
                payload=b"\x00update",
                payload_size=7,
                op_count=1,
            )
        )
    await db_session.flush()


async def test_history_list_query_count_is_bounded(
    db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    user = await UserFactory.create(db_session)
    project = await create_project(db_session, user.id, "P")
    doc = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)

    await _seed_history(db_session, project.id, doc.id, user.id, start=1, count=5)
    query_counter["count"] = 0
    await list_versions(db_session, doc.id, before=None, limit=100)
    with_five = query_counter["count"]

    await _seed_history(db_session, project.id, doc.id, user.id, start=6, count=25)
    query_counter["count"] = 0
    await list_versions(db_session, doc.id, before=None, limit=100)
    with_thirty = query_counter["count"]

    assert with_five == with_thirty  # bounded — author/label fetches are batched
    assert with_thirty <= 4  # rows + max-version + batched authors + batched labels


async def test_collaborators_list_query_count_is_bounded(
    db_session: AsyncSession, query_counter: dict[str, int]
) -> None:
    owner = await UserFactory.create(db_session)
    project = await create_project(db_session, owner.id, "P")

    async def _add_collaborators(count: int) -> None:
        for _ in range(count):
            member = await UserFactory.create(db_session)
            db_session.add(
                ProjectMembership(
                    project_id=project.id,
                    user_id=member.id,
                    role=MembershipRole.editor,
                    status=MembershipStatus.active,
                )
            )
        await db_session.flush()

    await _add_collaborators(5)
    query_counter["count"] = 0
    members_five = await sharing.list_members(db_session, project.id, owner.id)
    with_five = query_counter["count"]
    assert len(members_five) == 6  # owner + 5

    await _add_collaborators(25)
    query_counter["count"] = 0
    members_thirty = await sharing.list_members(db_session, project.id, owner.id)
    with_thirty = query_counter["count"]
    assert len(members_thirty) == 31  # owner + 30

    assert with_five == with_thirty  # users joined eagerly — no per-row lazy load
    assert with_thirty <= 3


# --- DB connection pool: config + no leak (AC8) ----------------------------- #


async def test_db_pool_uses_config_and_returns_to_baseline(settings_override: Any) -> None:
    settings = settings_override
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    try:
        assert engine.pool.size() == settings.db_pool_size  # pool sized from config
        for _ in range(20):
            async with sessionmaker() as session:
                await session.execute(text("SELECT 1"))
        # Every session was released — no connection leaked back into the pool.
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()
