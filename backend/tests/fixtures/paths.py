"""Shared constants for the test fixtures (spec 04)."""

from __future__ import annotations

from pathlib import Path

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

DEFAULT_TEST_DB = "postgresql+asyncpg://inkstave:inkstave@localhost:5432/inkstave_test"
