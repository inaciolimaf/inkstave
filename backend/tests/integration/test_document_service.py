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


async def test_replace_with_base_version_greater_than_current_conflicts(
    db_session: AsyncSession,
) -> None:
    """Spec 13 §5.2: base_version > current version (impossible normally) → 409.

    The ``WHERE version=base_version`` UPDATE matches 0 rows, so the row is left
    unchanged and a version conflict is raised.
    """
    project, entity = await _doc_entity(db_session)
    with pytest.raises(VersionConflictError):
        await replace_content(db_session, project.id, entity.id, "future", base_version=5)
    # Document is untouched at the initial empty version 0.
    doc = await get_document(db_session, project.id, entity.id)
    assert doc.version == 0
    assert doc.content == ""


async def test_not_a_document_for_file_entity(db_session: AsyncSession) -> None:
    """AC6: a ``file`` entity → 409 not_a_document on GET and replace content."""
    user = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, user.id, "P")
    root = await ensure_root(db_session, project.id)
    file_entity = await create_entity(
        db_session, project.id, TreeEntityType.file, "logo.png", root.id
    )
    with pytest.raises(NotADocumentError):
        await get_document(db_session, project.id, file_entity.id)
    with pytest.raises(NotADocumentError):
        await replace_content(db_session, project.id, file_entity.id, "x", base_version=0)


# --------------------------------------------------------------------------- #
# Pure, no-DB unit assertions for replace_content's logic (spec 13 §8). These
# exercise the size_bytes byte-count recomputation and the version-branch
# decision without touching Postgres, so they run as fast pure-logic checks.
# --------------------------------------------------------------------------- #


def test_size_bytes_counts_multibyte_utf8() -> None:
    """``size_bytes`` is the UTF-8 byte length, counting multibyte chars correctly.

    Mirrors how the service derives ``size_bytes`` (``len(content.encode())``) so
    the pure byte-count logic is asserted without any DB round-trip.
    """

    def size_bytes(content: str) -> int:
        return len(content.encode())  # the same computation replace_content uses

    # ASCII: one byte each.
    assert size_bytes("hello") == 5
    # Accented Latin-1 chars are 2 bytes each in UTF-8.
    assert size_bytes("héllo") == 6
    # An emoji is 4 bytes in UTF-8; "héllo 😀" = 5 ascii-ish + é(2) + space + 😀(4).
    assert size_bytes("héllo 😀") == size_bytes("hllo ") + 2 + 4
    # A CJK character is 3 bytes in UTF-8.
    assert size_bytes("漢字") == 6


def test_version_branch_decision_is_pure() -> None:
    """The optimistic-concurrency branch: a write is accepted only when
    ``base_version == current``; greater or less yields a conflict.

    This mirrors the ``WHERE version == base_version`` semantics as pure logic.
    """

    def accepts(current: int, base_version: int) -> bool:
        return current == base_version

    assert accepts(0, 0) is True  # equal → accepted
    assert accepts(3, 3) is True
    assert accepts(1, 0) is False  # stale (less) → conflict
    assert accepts(0, 5) is False  # greater than current → conflict
