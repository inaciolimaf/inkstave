"""Project file blobs leave object storage once the rows that name them are gone (specs 11, 14).

The keys are read before the delete and removed after the commit, through
``infra.storage.after_commit``: a rolled-back delete keeps its blobs, and a failed blob delete is
logged, not raised. Tree deletes reach :func:`purge_file_blobs_for_deleted` through the
``on_entities_deleted`` registry, which the composition root connects (as for history blobs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.infra.storage.after_commit import schedule_delete_after_commit
from inkstave.modules.projects.models.file import File

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.infra.storage.base import ObjectStore


async def purge_file_blobs_for_deleted(
    session: AsyncSession, store: ObjectStore | None, entity_ids: list[UUID]
) -> None:
    """The ``on_entities_deleted`` listener: the file blobs of the entities a delete removes."""
    if store is None or not entity_ids:
        return
    keys = await session.scalars(select(File.storage_key).where(File.entity_id.in_(entity_ids)))
    schedule_delete_after_commit(session, store, list(keys))


async def purge_file_blobs_for_project(session: AsyncSession, store: ObjectStore, project_id: UUID) -> None:
    """Schedule every file blob of a project for deletion once ``session`` commits (project delete)."""
    keys = await session.scalars(select(File.storage_key).where(File.project_id == project_id))
    schedule_delete_after_commit(session, store, list(keys))
