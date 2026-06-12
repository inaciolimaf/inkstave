"""File-tree service: create/rename/move/delete/list with path safety (spec 12).

All operations are scoped by ``project_id`` — an ``entity_id`` is never trusted
alone (``WHERE id = ? AND project_id = ?``). "Parent must be a folder" is
enforced here (the DB cannot express it without a trigger). Paths are derived,
not stored.

Error types and the pure tree-building helpers live in sibling modules
(:mod:`inkstave.services.tree_errors`, :mod:`inkstave.services.tree_builder`)
and are re-exported here so existing import paths keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.services.safe_path import validate_name_segment
from inkstave.services.tree_builder import build_tree, compute_path
from inkstave.services.tree_errors import (
    EntityNotFoundError,
    NameConflictError,
    ParentNotAFolderError,
    ParentNotFoundError,
    RootImmutableError,
    TreeCycleError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.storage.base import ObjectStore

__all__ = [
    "EntityNotFoundError",
    "NameConflictError",
    "ParentNotAFolderError",
    "ParentNotFoundError",
    "RootImmutableError",
    "TreeCycleError",
    "build_tree",
    "compute_path",
    "create_entity",
    "delete_entity",
    "ensure_root",
    "get_tree",
    "is_descendant",
    "move_entity",
    "rename_entity",
]


# --------------------------------------------------------------------------- #
# Queries / operations
# --------------------------------------------------------------------------- #


async def get_tree(session: AsyncSession, project_id: UUID) -> list[TreeEntity]:
    rows = await session.execute(select(TreeEntity).where(TreeEntity.project_id == project_id))
    return list(rows.scalars())


async def ensure_root(session: AsyncSession, project_id: UUID) -> TreeEntity:
    """Return the project's root folder, creating it if absent (idempotent)."""
    existing = (
        await session.execute(
            select(TreeEntity).where(
                TreeEntity.project_id == project_id, TreeEntity.is_root.is_(True)
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    root = TreeEntity(
        project_id=project_id,
        parent_id=None,
        type=TreeEntityType.folder,
        name="",
        is_root=True,
    )
    session.add(root)
    await session.flush()
    await session.refresh(root)
    return root


async def _get_entity(session: AsyncSession, project_id: UUID, entity_id: UUID) -> TreeEntity:
    entity = (
        await session.execute(
            select(TreeEntity).where(
                TreeEntity.id == entity_id, TreeEntity.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if entity is None:
        raise EntityNotFoundError()
    return entity


async def _sibling_exists(
    session: AsyncSession, parent_id: UUID, name: str, exclude_id: UUID | None = None
) -> bool:
    stmt = select(TreeEntity.id).where(
        TreeEntity.parent_id == parent_id,
        func.lower(TreeEntity.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(TreeEntity.id != exclude_id)
    return (await session.execute(stmt)).first() is not None


async def is_descendant(
    session: AsyncSession, project_id: UUID, ancestor_id: UUID, candidate_id: UUID
) -> bool:
    """True if ``candidate_id`` is ``ancestor_id`` or anywhere in its subtree."""
    sql = text(
        """
        WITH RECURSIVE subtree AS (
            SELECT id FROM tree_entities WHERE id = :anc AND project_id = :pid
            UNION ALL
            SELECT t.id FROM tree_entities t
            JOIN subtree s ON t.parent_id = s.id
            WHERE t.project_id = :pid
        )
        SELECT 1 FROM subtree WHERE id = :cand LIMIT 1
        """
    )
    row = (
        await session.execute(sql, {"anc": ancestor_id, "pid": project_id, "cand": candidate_id})
    ).first()
    return row is not None


async def create_entity(
    session: AsyncSession,
    project_id: UUID,
    type_: TreeEntityType,
    name: str,
    parent_id: UUID | None,
) -> TreeEntity:
    clean = validate_name_segment(name)
    if parent_id is None:
        parent = await ensure_root(session, project_id)
    else:
        parent = await _get_entity_as_parent(session, project_id, parent_id)

    if await _sibling_exists(session, parent.id, clean):
        raise NameConflictError()

    entity = TreeEntity(
        project_id=project_id,
        parent_id=parent.id,
        type=type_,
        name=clean,
        is_root=False,
    )
    session.add(entity)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise NameConflictError() from exc
    await session.refresh(entity)
    if entity.type is TreeEntityType.doc:
        # A doc entity always has an (initially empty) content row (spec 13).
        # Imported lazily to avoid a module-level import cycle.
        from inkstave.services.document_service import ensure_document

        await ensure_document(session, entity)
    return entity


async def _get_entity_as_parent(
    session: AsyncSession, project_id: UUID, parent_id: UUID
) -> TreeEntity:
    parent = (
        await session.execute(
            select(TreeEntity).where(
                TreeEntity.id == parent_id, TreeEntity.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if parent is None:
        raise ParentNotFoundError()
    if parent.type is not TreeEntityType.folder:
        raise ParentNotAFolderError()
    return parent


async def rename_entity(
    session: AsyncSession, project_id: UUID, entity_id: UUID, name: str
) -> TreeEntity:
    entity = await _get_entity(session, project_id, entity_id)
    if entity.is_root:
        raise RootImmutableError()
    clean = validate_name_segment(name)
    if entity.parent_id is not None and await _sibling_exists(
        session, entity.parent_id, clean, exclude_id=entity.id
    ):
        raise NameConflictError()
    entity.name = clean
    entity.updated_at = func.clock_timestamp()  # type: ignore[assignment]
    try:
        await session.flush()
    except IntegrityError as exc:
        raise NameConflictError() from exc
    await session.refresh(entity)
    return entity


async def move_entity(
    session: AsyncSession, project_id: UUID, entity_id: UUID, new_parent_id: UUID
) -> TreeEntity:
    entity = await _get_entity(session, project_id, entity_id)
    if entity.is_root:
        raise RootImmutableError()
    await _get_entity_as_parent(session, project_id, new_parent_id)

    if await is_descendant(session, project_id, entity.id, new_parent_id):
        raise TreeCycleError()
    if await _sibling_exists(session, new_parent_id, entity.name, exclude_id=entity.id):
        raise NameConflictError()

    entity.parent_id = new_parent_id
    entity.updated_at = func.clock_timestamp()  # type: ignore[assignment]
    try:
        await session.flush()
    except IntegrityError as exc:
        raise NameConflictError() from exc
    await session.refresh(entity)
    return entity


async def _file_keys_in_subtree(
    session: AsyncSession, project_id: UUID, entity_id: UUID
) -> list[str]:
    sql = text(
        """
        WITH RECURSIVE subtree AS (
            SELECT id FROM tree_entities WHERE id = :eid AND project_id = :pid
            UNION ALL
            SELECT t.id FROM tree_entities t
            JOIN subtree s ON t.parent_id = s.id
            WHERE t.project_id = :pid
        )
        SELECT f.storage_key FROM files f JOIN subtree s ON f.entity_id = s.id
        """
    )
    rows = (await session.execute(sql, {"eid": entity_id, "pid": project_id})).all()
    return [row[0] for row in rows]


async def delete_entity(
    session: AsyncSession,
    project_id: UUID,
    entity_id: UUID,
    store: ObjectStore | None = None,
) -> None:
    entity = await _get_entity(session, project_id, entity_id)
    if entity.is_root:
        raise RootImmutableError()
    # Collect blob keys before the cascade removes the rows.
    keys = await _file_keys_in_subtree(session, project_id, entity_id) if store else []
    # The self-FK ON DELETE CASCADE removes the whole subtree.
    await session.execute(
        delete(TreeEntity).where(TreeEntity.id == entity_id, TreeEntity.project_id == project_id)
    )
    await session.flush()
    # Best-effort blob cleanup after the DB delete (storage is not transactional).
    for key in keys:
        if store is not None:
            await store.delete(key)
