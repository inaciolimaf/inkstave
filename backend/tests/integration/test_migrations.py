"""Integration tests for the Alembic migration workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from inkstave.db.base import Base

pytestmark = pytest.mark.integration

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# Revisions immediately *before* the backfill migrations under test.
_BEFORE_TREE = "feb8f5c76b1a"  # 8b301674ef53 (tree) backfills a root per project
_BEFORE_SHARING = "b7c4e9d21f08"  # a1c2e3f40915 (sharing) backfills an owner membership


def test_migration_round_trip(_template_db: str) -> None:
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")  # restore the shared template DB to head


async def _seed_project(url: str) -> tuple[str, str]:
    """Insert a user + project at the current (pre-backfill) revision.

    Returns ``(user_id, project_id)``. Uses only columns that exist at the
    pre-tree / pre-sharing revisions (both predate memberships and tree rows).
    """
    user_id = str(uuid4())
    project_id = str(uuid4())
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, display_name) "
                    "VALUES (:id, :email, 'x', 'Owner')"
                ),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            await conn.execute(
                text("INSERT INTO projects (id, owner_id, name) VALUES (:id, :owner, 'P')"),
                {"id": project_id, "owner": user_id},
            )
    finally:
        await engine.dispose()
    return user_id, project_id


async def _scalar(url: str, sql: str, params: dict[str, Any]) -> Any:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params)).scalar_one()
    finally:
        await engine.dispose()


async def _cleanup(url: str, user_id: str, project_id: str) -> None:
    """Remove the directly-seeded rows so they don't leak into other tests.

    These migration tests write to the *shared template DB* outside the
    per-test rollback transaction (they must, to exercise real DDL/backfills),
    so they must clean up after themselves — otherwise the seeded user/project
    persist and pollute any later test sharing the same worker DB (e.g. the
    user-count assertion in test_register).
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM project_memberships WHERE project_id = :pid"),
                {"pid": project_id},
            )
            await conn.execute(
                text("DELETE FROM tree_entities WHERE project_id = :pid"),
                {"pid": project_id},
            )
            await conn.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
            await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    finally:
        await engine.dispose()


def test_tree_migration_backfills_a_root_for_existing_project(_template_db: str) -> None:
    """Spec 12 §8: a pre-existing project (no root) gets exactly one root on upgrade.

    Synchronous test: each async DB step runs in its own ``asyncio.run`` loop so it
    never overlaps Alembic's own ``command.*`` event loop (mixing the two in one
    running loop raises asyncpg "another operation in progress").
    """
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, _BEFORE_TREE)  # projects exist; tree_entities does not yet
    user_id = project_id = None
    try:
        user_id, project_id = asyncio.run(_seed_project(_template_db))
        command.upgrade(cfg, "head")  # runs the tree migration's root backfill
        roots = asyncio.run(
            _scalar(
                _template_db,
                "SELECT count(*) FROM tree_entities WHERE project_id = :pid AND is_root",
                {"pid": project_id},
            )
        )
        assert roots == 1
    finally:
        command.upgrade(cfg, "head")  # restore the shared template DB to head
        if user_id is not None and project_id is not None:
            asyncio.run(_cleanup(_template_db, user_id, project_id))


def test_sharing_migration_backfills_owner_membership(_template_db: str) -> None:
    """Spec 33 §8: a pre-existing project's owner gets an active owner membership."""
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, _BEFORE_SHARING)  # projects exist; memberships do not yet
    user_id = project_id = None
    try:
        user_id, project_id = asyncio.run(_seed_project(_template_db))
        command.upgrade(cfg, "head")  # runs the sharing migration's owner backfill
        count = asyncio.run(
            _scalar(
                _template_db,
                "SELECT count(*) FROM project_memberships "
                "WHERE project_id = :pid AND user_id = :uid "
                "AND role = 'owner' AND status = 'active'",
                {"pid": project_id, "uid": user_id},
            )
        )
        assert count == 1
    finally:
        command.upgrade(cfg, "head")  # restore the shared template DB to head
        if user_id is not None and project_id is not None:
            asyncio.run(_cleanup(_template_db, user_id, project_id))


async def test_autogenerate_is_empty(_template_db: str) -> None:
    engine = create_async_engine(_template_db)

    def _diffs(sync_conn: Any) -> list[Any]:
        ctx = MigrationContext.configure(
            sync_conn,
            opts={"compare_type": True, "compare_server_default": True},
        )
        return compare_metadata(ctx, Base.metadata)

    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(_diffs)
    finally:
        await engine.dispose()
    assert diffs == []
