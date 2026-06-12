"""Spec-57 integration tests: the first-admin bootstrap + setup endpoints, the
real advisory-locked migration runner, and demo seeding — against the test DB.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import build_password_hasher
from inkstave.bootstrap.admin import admin_exists, ensure_initial_admin
from inkstave.bootstrap.migrate import is_database_at_head, run_upgrade
from inkstave.bootstrap.seed import DEMO_EMAIL, seed_demo
from inkstave.config import Settings, get_settings
from inkstave.db.models.user import User

pytestmark = pytest.mark.integration


def _hasher() -> Any:
    return build_password_hasher(get_settings())


async def _admin_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        or 0
    )


# --- first-admin bootstrap service ------------------------------------------- #


async def test_ensure_initial_admin_creates_once_then_noops(db_session: AsyncSession) -> None:
    hasher = _hasher()
    admin = await ensure_initial_admin(
        db_session, hasher, email="admin@example.com", password="adminPass1", display_name="Admin"
    )
    assert admin is not None and admin.is_admin
    assert admin.hashed_password.startswith("$argon2")

    # A second call (even with different credentials) is a no-op — no second admin.
    again = await ensure_initial_admin(
        db_session, hasher, email="other@example.com", password="adminPass1", display_name="Other"
    )
    assert again is None
    assert await admin_exists(db_session)
    assert await _admin_count(db_session) == 1


# --- setup endpoints (mounted at /api/setup) --------------------------------- #


async def test_setup_status_then_admin_then_locked(async_client: AsyncClient) -> None:
    assert (await async_client.get("/api/setup/status")).json() == {"needs_setup": True}

    created = await async_client.post(
        "/api/setup/admin",
        json={"email": "founder@example.com", "password": "Str0ngP4ss", "display_name": "Founder"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "founder@example.com"

    assert (await async_client.get("/api/setup/status")).json() == {"needs_setup": False}

    # Locked forever once an admin exists — creates nothing.
    locked = await async_client.post(
        "/api/setup/admin",
        json={"email": "second@example.com", "password": "Str0ngP4ss", "display_name": "Two"},
    )
    assert locked.status_code == 409


async def test_setup_admin_second_attempt_creates_nothing(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Two sequential setups (the shared test session can't truly overlap): the
    # second is locked, so exactly one admin exists. Real concurrent safety comes
    # from the advisory lock in ensure_initial_admin.
    for _ in range(2):
        await async_client.post(
            "/api/setup/admin",
            json={"email": "founder@example.com", "password": "Str0ngP4ss", "display_name": "A"},
        )
    assert await _admin_count(db_session) == 1


# --- migration runner -------------------------------------------------------- #


async def test_run_upgrade_is_idempotent_against_test_db(
    db_engine: Any, settings_override: Settings
) -> None:
    # The test DB is already at head (conftest migrates the template). The
    # advisory-locked upgrade is a clean no-op, and re-running it is also a no-op.
    await asyncio.to_thread(run_upgrade, settings_override)
    await asyncio.to_thread(run_upgrade, settings_override)
    assert await is_database_at_head(db_engine)


# --- demo seed --------------------------------------------------------------- #


async def test_seed_demo_is_idempotent_in_dev(db_session: AsyncSession) -> None:
    hasher = _hasher()
    settings = get_settings()  # environment="test" — not production
    assert await seed_demo(db_session, hasher, settings=settings) is True
    # Re-running does not duplicate the demo user/project.
    assert await seed_demo(db_session, hasher, settings=settings) is False
    count = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == DEMO_EMAIL)
    )
    assert count == 1
