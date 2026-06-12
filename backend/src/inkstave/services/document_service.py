"""Document content service: version-checked reads/replaces (spec 13).

The replace is a single atomic ``UPDATE … WHERE entity_id = ? AND version = ?``,
so a stale ``base_version`` simply matches zero rows — preventing lost updates
without a row-lock round-trip.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select, update

from inkstave.config import get_settings
from inkstave.db.models.document import Document
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.errors import AppError, ConflictError
from inkstave.services.tree_service import EntityNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class NotADocumentError(ConflictError):
    error_type = "not_a_document"

    def __init__(self) -> None:
        super().__init__("This entity is not a document.")


class VersionConflictError(ConflictError):
    error_type = "version_conflict"

    def __init__(self, current_version: int, current_content: str) -> None:
        super().__init__(
            "The document was modified by someone else.",
            details=[{"current_version": current_version, "current_content": current_content}],
        )


class ContentTooLargeError(AppError):
    status_code = 413
    error_type = "content_too_large"

    def __init__(self) -> None:
        super().__init__("Document content exceeds the maximum allowed size.")


async def _get_doc_entity(session: AsyncSession, project_id: UUID, entity_id: UUID) -> TreeEntity:
    entity = (
        await session.execute(
            select(TreeEntity).where(
                TreeEntity.id == entity_id, TreeEntity.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if entity is None:
        raise EntityNotFoundError()
    if entity.type is not TreeEntityType.doc:
        raise NotADocumentError()
    return entity


async def ensure_document(session: AsyncSession, entity: TreeEntity) -> Document:
    """Return the entity's content row, creating an empty one if absent."""
    existing = (
        await session.execute(select(Document).where(Document.entity_id == entity.id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    document = Document(
        entity_id=entity.id,
        project_id=entity.project_id,
        content="",
        version=0,
        size_bytes=0,
    )
    session.add(document)
    await session.flush()
    await session.refresh(document)
    return document


async def get_document(session: AsyncSession, project_id: UUID, entity_id: UUID) -> Document:
    entity = await _get_doc_entity(session, project_id, entity_id)
    return await ensure_document(session, entity)


async def replace_content(
    session: AsyncSession,
    project_id: UUID,
    entity_id: UUID,
    content: str,
    base_version: int,
) -> Document:
    entity = await _get_doc_entity(session, project_id, entity_id)
    document = await ensure_document(session, entity)

    size_bytes = len(content.encode("utf-8"))
    if size_bytes > get_settings().max_document_bytes:
        raise ContentTooLargeError()

    stmt = (
        update(Document)
        .where(Document.entity_id == entity_id, Document.version == base_version)
        .values(
            content=content,
            version=base_version + 1,
            size_bytes=size_bytes,
            updated_at=func.clock_timestamp(),
        )
        .returning(Document.entity_id)
        .execution_options(synchronize_session=False)
    )
    matched = (await session.execute(stmt)).first() is not None
    await session.refresh(document)
    if not matched:
        # Stale base_version (or it was raced) -> the row is unchanged.
        raise VersionConflictError(document.version, document.content)
    return document


# --------------------------------------------------------------------------- #
# Collaboration bridge seam (spec 28): read/write the canonical text directly,
# bypassing optimistic-concurrency so the CRDT can keep spec-13 content in sync
# without re-emitting a CRDT update (avoids a feedback loop).
# --------------------------------------------------------------------------- #


async def read_content_for_collab(session: AsyncSession, entity_id: UUID) -> str:
    """Read a document's current content for the initial CRDT seed (``""`` if none)."""
    content = (
        await session.execute(select(Document.content).where(Document.entity_id == entity_id))
    ).scalar_one_or_none()
    return content or ""


async def set_content_from_collab(session: AsyncSession, entity_id: UUID, content: str) -> bool:
    """Write CRDT text into the spec-13 ``content`` column directly — no version
    check, no CRDT round-trip. Idempotent (a no-op when unchanged); bumps
    ``version`` only on a real change so REST optimistic-concurrency still works.
    Returns whether the content changed. Creates the row if absent.
    """
    current = (
        await session.execute(select(Document.content).where(Document.entity_id == entity_id))
    ).scalar_one_or_none()
    if current == content:
        return False
    size_bytes = len(content.encode("utf-8"))
    if current is None:
        entity = (
            await session.execute(select(TreeEntity).where(TreeEntity.id == entity_id))
        ).scalar_one_or_none()
        if entity is None or entity.type is not TreeEntityType.doc:
            return False
        session.add(
            Document(
                entity_id=entity_id,
                project_id=entity.project_id,
                content=content,
                version=1,
                size_bytes=size_bytes,
            )
        )
        await session.flush()
        return True
    await session.execute(
        update(Document)
        .where(Document.entity_id == entity_id)
        .values(
            content=content,
            version=Document.version + 1,
            size_bytes=size_bytes,
            updated_at=func.clock_timestamp(),
        )
    )
    await session.flush()
    return True
