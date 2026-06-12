"""Integration tests for the document content service (spec 13)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import (
    ContentTooLargeError,
    NotADocumentError,
    VersionConflictError,
    ensure_document,
    get_document,
    replace_content,
)
from inkstave.services.project import create_project
from inkstave.services.tree_service import create_entity, ensure_root
from tests.factories import UserFactory

pytestmark = pytest.mark.integration


async def _doc_entity(db_session: AsyncSession) -> tuple:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    root = await ensure_root(db_session, project.id)
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", root.id)
    return project, entity


async def test_doc_creation_yields_empty_document(db_session: AsyncSession) -> None:
    project, entity = await _doc_entity(db_session)
    doc = await get_document(db_session, project.id, entity.id)
    assert doc.content == ""
    assert doc.version == 0
    assert doc.size_bytes == 0


async def test_ensure_document_is_idempotent(db_session: AsyncSession) -> None:
    project, entity = await _doc_entity(db_session)
    first = await ensure_document(db_session, entity)
    second = await ensure_document(db_session, entity)
    assert first.entity_id == second.entity_id


async def test_not_a_document_for_folder(db_session: AsyncSession) -> None:
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    root = await ensure_root(db_session, project.id)
    folder = await create_entity(db_session, project.id, TreeEntityType.folder, "f", root.id)
    with pytest.raises(NotADocumentError):
        await get_document(db_session, project.id, folder.id)


async def test_replace_increments_version_and_size(db_session: AsyncSession) -> None:
    project, entity = await _doc_entity(db_session)
    doc = await replace_content(db_session, project.id, entity.id, "héllo 😀", base_version=0)
    assert doc.version == 1
    assert doc.content == "héllo 😀"
    assert doc.size_bytes == len("héllo 😀".encode())  # multibyte counted correctly


async def test_replace_with_stale_version_conflicts(db_session: AsyncSession) -> None:
    project, entity = await _doc_entity(db_session)
    await replace_content(db_session, project.id, entity.id, "v1", base_version=0)
    with pytest.raises(VersionConflictError):
        await replace_content(db_session, project.id, entity.id, "v2", base_version=0)
    # Unchanged at version 1.
    doc = await get_document(db_session, project.id, entity.id)
    assert doc.version == 1
    assert doc.content == "v1"


async def test_content_too_large(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave.config import get_settings

    monkeypatch.setenv("MAX_DOCUMENT_BYTES", "10")
    get_settings.cache_clear()
    project, entity = await _doc_entity(db_session)
    with pytest.raises(ContentTooLargeError):
        await replace_content(db_session, project.id, entity.id, "x" * 11, base_version=0)
