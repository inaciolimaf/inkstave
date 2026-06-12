"""Unit tests for the DB layer that need no database connection."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Column, Integer, Table, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from inkstave.db.base import NAMING_CONVENTION, Base
from inkstave.db.engine import check_db, normalize_async_dsn
from inkstave.db.models.ping import Ping
from tests.conftest import FakeEngineBroken, FakeEngineOk


def test_normalize_dsn_variants() -> None:
    assert normalize_async_dsn("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert normalize_async_dsn("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    already = "postgresql+asyncpg://u:p@h:5432/db"
    assert normalize_async_dsn(already) == already


def test_naming_convention_registered() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"


def test_ping_columns() -> None:
    columns = Ping.__table__.columns
    assert set(columns.keys()) == {"id", "note", "created_at", "updated_at"}
    assert columns["id"].primary_key is True
    assert columns["created_at"].type.timezone is True  # type: ignore[attr-defined]
    assert columns["updated_at"].onupdate is not None
    assert columns["note"].type.length == 200  # type: ignore[attr-defined]


def test_unique_constraint_naming() -> None:
    table = Table("widgets_tmp", Base.metadata, Column("kind", Integer), UniqueConstraint("kind"))
    try:
        ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "uq_widgets_tmp_kind" in ddl
    finally:
        Base.metadata.remove(table)


async def test_check_db_with_fakes() -> None:
    ok: Any = FakeEngineOk()
    broken: Any = FakeEngineBroken()
    assert await check_db(ok, 0.5) is True
    assert await check_db(broken, 0.5) is False
