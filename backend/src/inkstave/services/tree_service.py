"""File-tree service: create/rename/move/delete/list with path safety (spec 12).

All operations are scoped by ``project_id`` — an ``entity_id`` is never trusted
alone (``WHERE id = ? AND project_id = ?``). "Parent must be a folder" is
enforced here (the DB cannot express it without a trigger). Paths are derived,
not stored.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.errors import AppError, ConflictError, NotFoundError
from inkstave.schemas.tree import TreeEntityTypeLiteral, TreeNode, TreeRead
from inkstave.services.safe_path import validate_name_segment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.storage.base import ObjectStore


class EntityNotFoundError(NotFoundError):
    error_type = "entity_not_found"

    def __init__(self) -> None:
        super().__init__("Tree entity not found.")


class ParentNotFoundError(NotFoundError):
    error_type = "parent_not_found"

    def __init__(self) -> None:
        super().__init__("Parent folder not found.")


class ParentNotAFolderError(AppError):
    status_code = 422
    error_type = "parent_not_a_folder"

    def __init__(self) -> None:
        super().__init__("Parent must be a folder.")


class NameConflictError(ConflictError):
    error_type = "name_conflict"

    def __init__(self) -> None:
        super().__init__("An entity with this name already exists in the folder.")


class TreeCycleError(ConflictError):
    error_type = "tree_cycle"

    def __init__(self) -> None:
        super().__init__("Cannot move a folder into itself or a descendant.")


class RootImmutableError(ConflictError):
    error_type = "root_immutable"

    def __init__(self) -> None:
        super().__init__("The project root cannot be modified.")


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def compute_path(entity: TreeEntity, by_id: dict[UUID, TreeEntity]) -> str:
    """Derive ``a/b/c`` from the ancestor chain (root excluded)."""
    segments: list[str] = []
    current: TreeEntity | None = entity
    while current is not None and not current.is_root:
        segments.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id is not None else None
    return "/".join(reversed(segments))


def build_tree(entities: list[TreeEntity]) -> TreeRead:
    """Assemble a flat entity list into a nested :class:`TreeRead`."""
    by_id = {e.id: e for e in entities}
    children_map: dict[UUID, list[TreeEntity]] = defaultdict(list)
    root: TreeEntity | None = None
    for entity in entities:
        if entity.is_root:
            root = entity
        elif entity.parent_id is not None:
            children_map[entity.parent_id].append(entity)
    if root is None:
        raise EntityNotFoundError()
    return TreeRead(root=_to_node(root, by_id, children_map))


def _to_node(
    entity: TreeEntity,
    by_id: dict[UUID, TreeEntity],
    children_map: dict[UUID, list[TreeEntity]],
) -> TreeNode:
    children: list[TreeNode] | None
    if entity.type is TreeEntityType.folder:
        # Folders first, then docs/files, each group by lower(name).
        kids = sorted(
            children_map.get(entity.id, []),
            key=lambda c: (c.type is not TreeEntityType.folder, c.name.lower()),
        )
        children = [_to_node(k, by_id, children_map) for k in kids]
    else:
        children = None
    return TreeNode(
        id=entity.id,
        project_id=entity.project_id,
        parent_id=entity.parent_id,
        type=cast(TreeEntityTypeLiteral, entity.type.value),
        name=entity.name,
        is_root=entity.is_root,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        path=compute_path(entity, by_id),
        children=children,
    )


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
