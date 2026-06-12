"""Integration tests for the Alembic migration workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from inkstave.db.base import Base

pytestmark = pytest.mark.integration

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def test_migration_round_trip(_template_db: str) -> None:
    cfg = Config(str(_ALEMBIC_INI))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")  # restore the shared template DB to head


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
