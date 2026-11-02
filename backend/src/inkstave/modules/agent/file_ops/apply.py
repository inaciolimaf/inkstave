"""Carries out a proposed file operation, once the user has asked for it.

This runs only from the apply route, on the user's own request and role: no tool and no
graph node reaches it. Every step shares the request's transaction, so an operation that
fails halfway leaves nothing behind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.core.errors import ConflictError
from inkstave.modules.agent.file_ops.models import ProposedFileOp, ProposedFileOpStatus
from inkstave.modules.agent.file_ops.paths import ancestors_of, name_of, parent_of, subtree_paths
from inkstave.modules.projects import (
    ParentNotAFolderError,
    TreeEntity,
    TreeEntityType,
    compute_path,
    create_entity,
    delete_entity,
    get_tree,
    move_entity,
    rename_entity,
    set_content_from_collab,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.infra.storage.base import ObjectStore


class FileOpClosedError(ConflictError):
    error_type = "file_op_closed"

    def __init__(self) -> None:
        super().__init__("This proposal was already decided.")


class FileOpStaleError(ConflictError):
    error_type = "file_op_stale"

    def __init__(self) -> None:
        super().__init__("The project changed since this was proposed. Ask the agent to propose it again.")


async def _paths_by_id(db: AsyncSession, project_id: UUID) -> dict[UUID, str]:
    entities = await get_tree(db, project_id)
    by_id = {e.id: e for e in entities}
    return {e.id: compute_path(e, by_id) for e in entities if not e.is_root}


async def _ensure_folders(db: AsyncSession, project_id: UUID, folder: str) -> UUID | None:
    """The id of ``folder``, creating what is missing; ``None`` for the project root."""
    entities = await get_tree(db, project_id)
    by_id = {e.id: e for e in entities}
    by_path = {compute_path(e, by_id).lower(): e for e in entities if not e.is_root}
    parent: TreeEntity | None = None
    for path in ancestors_of(f"{folder}/x") if folder else []:
        found = by_path.get(path.lower())
        if found is not None and found.type is not TreeEntityType.folder:
            raise ParentNotAFolderError()
        parent = found or await create_entity(
            db, project_id, TreeEntityType.folder, name_of(path), parent.id if parent else None
        )
    return parent.id if parent else None


async def _create(db: AsyncSession, op: ProposedFileOp, _store: ObjectStore) -> None:
    parent_id = await _ensure_folders(db, op.project_id, parent_of(op.path))
    entity_type = TreeEntityType(op.entity_type)
    entity = await create_entity(db, op.project_id, entity_type, name_of(op.path), parent_id)
    if entity_type is TreeEntityType.doc and op.content:
        await set_content_from_collab(db, entity.id, op.content)
    op.entity_id = entity.id


async def _target(db: AsyncSession, op: ProposedFileOp) -> tuple[UUID, dict[UUID, str]]:
    """The entity the proposal named, refused when it is no longer where the user saw it."""
    paths = await _paths_by_id(db, op.project_id)
    if op.entity_id is None or paths.get(op.entity_id) != op.path:
        raise FileOpStaleError()
    return op.entity_id, paths


async def _delete(db: AsyncSession, op: ProposedFileOp, store: ObjectStore) -> None:
    entity_id, paths = await _target(db, op)
    # The user approved a list of what goes away; anything added since was not on it.
    if subtree_paths(paths.values(), op.path) != op.affected_paths:
        raise FileOpStaleError()
    await delete_entity(db, op.project_id, entity_id, store=store)


async def _move(db: AsyncSession, op: ProposedFileOp, _store: ObjectStore) -> None:
    entity_id, _paths = await _target(db, op)
    new_path = op.new_path
    if new_path is None:
        raise FileOpStaleError()
    if parent_of(new_path).lower() != parent_of(op.path).lower():
        parent_id = await _ensure_folders(db, op.project_id, parent_of(new_path))
        root_id = await _root_id(db, op.project_id)
        await move_entity(db, op.project_id, entity_id, parent_id or root_id)
    if name_of(new_path) != name_of(op.path):
        await rename_entity(db, op.project_id, entity_id, name_of(new_path))


async def _root_id(db: AsyncSession, project_id: UUID) -> UUID:
    return next(e.id for e in await get_tree(db, project_id) if e.is_root)


_HANDLERS = {"create": _create, "delete": _delete, "move": _move}


async def apply_file_op(db: AsyncSession, op: ProposedFileOp, *, store: ObjectStore) -> None:
    """Carry out one open proposal and record it as applied."""
    if op.status != ProposedFileOpStatus.proposed.value:
        raise FileOpClosedError()
    await _HANDLERS[op.kind](db, op, store)
    op.status = ProposedFileOpStatus.applied.value
    await db.flush()


async def reject_file_op(db: AsyncSession, op: ProposedFileOp) -> None:
    if op.status != ProposedFileOpStatus.proposed.value:
        raise FileOpClosedError()
    op.status = ProposedFileOpStatus.rejected.value
    await db.flush()
