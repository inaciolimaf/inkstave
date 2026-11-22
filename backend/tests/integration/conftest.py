"""Fixtures for the integration tier: the "lived-in" project of ``test_seeded_*`` (see tests/factories)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.infra.deps import get_object_store
from tests.factories import LivedInProject, build_lived_in_project
from tests.integration._files_api_support import InMemoryObjectStore


@pytest_asyncio.fixture
async def lived_in_store(app: Any) -> InMemoryObjectStore:
    """The in-memory object store, also served to the API as its blob store."""
    store = InMemoryObjectStore()
    app.dependency_overrides[get_object_store] = lambda: store
    return store


@pytest_asyncio.fixture
async def lived_in_project(
    db_session: AsyncSession, lived_in_store: InMemoryObjectStore
) -> AsyncIterator[LivedInProject]:
    """A project with content, history, comments, a proposal, a share link and a collaborator."""
    lived = await build_lived_in_project(db_session, lived_in_store)
    await db_session.commit()
    yield lived
