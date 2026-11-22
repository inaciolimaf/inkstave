"""The import job is enqueued only after the request's transaction has committed (spec 101).

A worker that picks the job up before the commit finds no row, returns, and with ``max_tries=1``
the import stays ``queued`` forever. The route creates the row, the session dependency commits,
and only then a background task enqueues the job.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.infra.storage.base import ObjectStore
from inkstave.modules.projects.deps import get_import_enqueuer
from inkstave.modules.projects.models.project_import import ProjectImport
from tests.integration._project_import_support import (
    FakeImportEnqueuer,
    auth,
    install_store,
    make_zip,
    post_import,
)

pytestmark = pytest.mark.integration


class _OrderedEnqueuer(FakeImportEnqueuer):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def enqueue(self, import_id: UUID) -> str | None:
        self._events.append("enqueue")
        return await super().enqueue(import_id)


class _FailingEnqueuer:
    async def enqueue(self, import_id: UUID) -> str | None:
        raise ConnectionError("redis is down")


@pytest.fixture
def store(app: Any) -> ObjectStore:
    return install_store(app)


async def test_job_is_enqueued_after_the_commit(
    app: Any, async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    events: list[str] = []
    enqueuer = _OrderedEnqueuer(events)
    app.dependency_overrides[get_import_enqueuer] = lambda: enqueuer
    commit = db_session.commit

    async def recording_commit() -> None:
        events.append("commit")
        await commit()

    db_session.commit = recording_commit  # type: ignore[method-assign]  # replaces a method with a test double
    try:
        headers = await auth(db_session)
        resp = await post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
    finally:
        db_session.commit = commit  # type: ignore[method-assign]  # replaces a method with a test double
    assert resp.status_code == 202
    assert events.index("commit") < events.index("enqueue")
    # The job id is stored on the row the job reads.
    import_id = UUID(resp.json()["import_id"])
    row = (await db_session.execute(select(ProjectImport).where(ProjectImport.id == import_id))).scalar_one()
    assert row.job_id == f"job-{import_id}"


async def test_enqueue_failure_marks_the_import_error_and_drops_the_blob(
    app: Any, async_client: AsyncClient, db_session: AsyncSession, store: ObjectStore
) -> None:
    app.dependency_overrides[get_import_enqueuer] = lambda: _FailingEnqueuer()
    headers = await auth(db_session)
    resp = await post_import(async_client, headers, make_zip({"main.tex": b"\\documentclass{a}"}))
    # The project and the row are committed; the failed enqueue ends the import as an error
    # instead of leaving it queued with no job, and the staged archive is removed.
    assert resp.status_code == 202
    import_id = UUID(resp.json()["import_id"])
    row = (await db_session.execute(select(ProjectImport).where(ProjectImport.id == import_id))).scalar_one()
    assert row.status == "error"
    assert row.error_type == "enqueue_failed"
    # The staged archive goes in the background, after the commit: poll with a deadline.
    for _ in range(500):
        if not [key for key in store._d if key.startswith("imports/")]:  # type: ignore[attr-defined]  # reads a private or fake attribute that the real type does not declare
            break
        await asyncio.sleep(0.01)
    assert not [key for key in store._d if key.startswith("imports/")]  # type: ignore[attr-defined]  # reads a private or fake attribute that the real type does not declare
