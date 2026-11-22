"""The lived-in project builder writes what the other ``test_seeded_*`` tests start from."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.discussion.comments.models import CommentThread
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate
from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.file import File
from inkstave.modules.projects.models.share_link import ProjectShareLink
from tests.factories.lived_in import (
    DOC_CONTENTS,
    FILE_PATH,
    MAIN_TEX,
    PLOT_PNG,
    LivedInProject,
    build_lived_in_project,
)
from tests.integration._files_api_support import InMemoryObjectStore

pytestmark = pytest.mark.integration


async def test_seeded_documents_hold_their_content(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    rows = await db_session.scalars(
        select(Document).where(Document.project_id == lived_in_project.project_id)
    )
    contents = {doc.entity_id: doc.content for doc in rows}
    assert len(contents) == len(DOC_CONTENTS)
    for path, text in DOC_CONTENTS.items():
        assert contents[lived_in_project.ids[path]] == text
    assert "\\input{chapters/intro}" in MAIN_TEX


async def test_seeded_main_has_history_and_the_older_document_has_none(
    db_session: AsyncSession, lived_in_project: LivedInProject
) -> None:
    main_id = lived_in_project.main_id
    appendix_id = lived_in_project.ids["appendix.tex"]
    updates = await db_session.scalar(
        select(func.count()).select_from(HistoryUpdate).where(HistoryUpdate.doc_id == main_id)
    )
    assert updates == 2
    assert (
        await db_session.scalar(
            select(func.count()).select_from(HistoryChunk).where(HistoryChunk.doc_id == appendix_id)
        )
        == 0
    )

    replay = YDocument()
    chunk = await db_session.scalar(select(HistoryChunk).where(HistoryChunk.doc_id == main_id))
    assert chunk is not None
    replay.apply_update(chunk.base_snapshot or b"")
    for update in await db_session.scalars(
        select(HistoryUpdate).where(HistoryUpdate.doc_id == main_id).order_by(HistoryUpdate.version)
    ):
        assert update.payload is not None
        replay.apply_update(update.payload)
    assert replay.text == MAIN_TEX


async def test_seeded_binary_blob_and_collaboration_rows(
    db_session: AsyncSession, lived_in_project: LivedInProject, lived_in_store: InMemoryObjectStore
) -> None:
    file_row = await db_session.get(File, lived_in_project.ids[FILE_PATH])
    assert file_row is not None
    assert file_row.size_bytes == len(PLOT_PNG)
    stat, stream = await lived_in_store.open(file_row.storage_key)
    assert b"".join([chunk async for chunk in stream]) == PLOT_PNG
    assert stat.size == len(PLOT_PNG)

    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ProjectShareLink)
            .where(ProjectShareLink.project_id == lived_in_project.project_id)
        )
        == 1
    )
    thread = await db_session.get(CommentThread, lived_in_project.thread_id)
    assert thread is not None
    assert thread.document_id == lived_in_project.ids["chapters/intro.tex"]


async def test_seeded_builder_is_fast(db_session: AsyncSession) -> None:
    started = time.perf_counter()
    await build_lived_in_project(db_session, InMemoryObjectStore(), name="Second")
    elapsed = time.perf_counter() - started
    # About 0.1 s alone; the bound leaves room for a loaded parallel run (CI has no retries).
    assert elapsed < 1.0, f"lived-in builder took {elapsed * 1000:.0f} ms"
