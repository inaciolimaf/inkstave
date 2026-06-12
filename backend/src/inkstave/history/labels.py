"""History labels (named checkpoints) — doc-level and project-level (spec 37)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.db.models.document import Document
from inkstave.db.models.history import HistoryLabel, HistoryUpdate
from inkstave.errors import ConflictError, NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class LabelNotFoundError(NotFoundError):
    error_type = "label_not_found"

    def __init__(self) -> None:
        super().__init__("Label not found.")


class DuplicateLabelError(ConflictError):
    error_type = "duplicate_label"

    def __init__(self) -> None:
        super().__init__("A label with that name already exists.")


async def ensure_label_available(session: AsyncSession, *, doc_id: UUID, name: str) -> None:
    """Raise DuplicateLabelError if a label with ``name`` already exists on the doc."""
    existing = await session.scalar(
        select(HistoryLabel.id).where(HistoryLabel.doc_id == doc_id, HistoryLabel.name == name)
    )
    if existing is not None:
        raise DuplicateLabelError()


async def create_doc_label(
    session: AsyncSession,
    *,
    project_id: UUID,
    doc_id: UUID,
    version: int,
    name: str,
    created_by: UUID | None,
) -> HistoryLabel:
    await ensure_label_available(session, doc_id=doc_id, name=name)
    label = HistoryLabel(
        project_id=project_id,
        doc_id=doc_id,
        version=version,
        name=name,
        created_by=created_by,
    )
    session.add(label)
    await session.flush()
    return label


async def list_doc_labels(session: AsyncSession, doc_id: UUID) -> list[HistoryLabel]:
    return list(
        (
            await session.execute(
                select(HistoryLabel)
                .where(HistoryLabel.doc_id == doc_id)
                .order_by(HistoryLabel.created_at.desc())
            )
        ).scalars()
    )


async def delete_doc_label(
    session: AsyncSession, *, project_id: UUID, doc_id: UUID, label_id: UUID
) -> None:
    label = await session.scalar(
        select(HistoryLabel).where(
            HistoryLabel.id == label_id,
            HistoryLabel.doc_id == doc_id,
            HistoryLabel.project_id == project_id,
        )
    )
    if label is None:
        raise LabelNotFoundError()
    await session.delete(label)
    await session.flush()


async def create_project_label(
    session: AsyncSession, *, project_id: UUID, name: str, created_by: UUID | None
) -> HistoryLabel:
    existing = await session.scalar(
        select(HistoryLabel.id).where(
            HistoryLabel.project_id == project_id,
            HistoryLabel.doc_id.is_(None),
            HistoryLabel.name == name,
        )
    )
    if existing is not None:
        raise DuplicateLabelError()
    # Snapshot every document's current history version at this moment.
    rows = (
        await session.execute(
            select(HistoryUpdate.doc_id, func.max(HistoryUpdate.version))
            .join(Document, Document.entity_id == HistoryUpdate.doc_id)
            .where(Document.project_id == project_id)
            .group_by(HistoryUpdate.doc_id)
        )
    ).all()
    payload = {str(doc_id): int(version) for doc_id, version in rows}
    label = HistoryLabel(
        project_id=project_id,
        doc_id=None,
        version=0,
        name=name,
        created_by=created_by,
        payload=payload,
    )
    session.add(label)
    await session.flush()
    return label


async def list_project_labels(session: AsyncSession, project_id: UUID) -> list[HistoryLabel]:
    return list(
        (
            await session.execute(
                select(HistoryLabel)
                .where(HistoryLabel.project_id == project_id, HistoryLabel.doc_id.is_(None))
                .order_by(HistoryLabel.created_at.desc())
            )
        ).scalars()
    )


async def delete_project_label(session: AsyncSession, *, project_id: UUID, label_id: UUID) -> None:
    label = await session.scalar(
        select(HistoryLabel).where(
            HistoryLabel.id == label_id,
            HistoryLabel.project_id == project_id,
            HistoryLabel.doc_id.is_(None),
        )
    )
    if label is None:
        raise LabelNotFoundError()
    await session.delete(label)
    await session.flush()


async def get_project_label(
    session: AsyncSession, *, project_id: UUID, label_id: UUID
) -> HistoryLabel:
    label = await session.scalar(
        select(HistoryLabel).where(
            HistoryLabel.id == label_id,
            HistoryLabel.project_id == project_id,
            HistoryLabel.doc_id.is_(None),
        )
    )
    if label is None:
        raise LabelNotFoundError()
    return label
