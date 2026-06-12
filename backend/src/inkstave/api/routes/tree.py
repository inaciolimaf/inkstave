"""File-tree routes (spec 12), scoped to an owned project.

Every route resolves ``project_id`` through the spec-11 ownership rule first
(``get_owned_project`` → 404 ``project_not_found`` when missing/not-owned).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, status

from inkstave.auth.dependencies import get_current_user
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_object_store
from inkstave.errors import ErrorEnvelope
from inkstave.schemas.tree import (
    CreateEntityIn,
    MoveEntityIn,
    RenameEntityIn,
    TreeEntityRead,
    TreeEntityTypeLiteral,
    TreeRead,
)
from inkstave.services import tree_service
from inkstave.services.project import get_owned_project

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.db.models.project import Project
    from inkstave.db.models.user import User
    from inkstave.storage.base import ObjectStore

router = APIRouter(prefix="/projects/{project_id}/tree", tags=["tree"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorEnvelope},
}


async def owned_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Project:
    """Resolve the owned project or raise 404 (existence is not leaked)."""
    return await get_owned_project(session, user.id, project_id)


async def _read(session: AsyncSession, project_id: UUID, entity: TreeEntity) -> TreeEntityRead:
    entities = await tree_service.get_tree(session, project_id)
    by_id = {e.id: e for e in entities}
    return TreeEntityRead(
        id=entity.id,
        project_id=entity.project_id,
        parent_id=entity.parent_id,
        type=cast(TreeEntityTypeLiteral, entity.type.value),
        name=entity.name,
        is_root=entity.is_root,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        path=tree_service.compute_path(entity, by_id),
    )


@router.get("", response_model=TreeRead, summary="List the project's file tree")
async def get_tree(
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> TreeRead:
    entities = await tree_service.get_tree(session, project.id)
    return tree_service.build_tree(entities)


@router.post(
    "/entities",
    status_code=status.HTTP_201_CREATED,
    response_model=TreeEntityRead,
    summary="Create a folder or document entity",
    responses=_ERRORS,
)
async def create_entity(
    data: CreateEntityIn,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> TreeEntityRead:
    entity = await tree_service.create_entity(
        session, project.id, TreeEntityType(data.type), data.name, data.parent_id
    )
    return await _read(session, project.id, entity)


@router.patch(
    "/entities/{entity_id}/rename",
    response_model=TreeEntityRead,
    summary="Rename a tree entity",
    responses=_ERRORS,
)
async def rename_entity(
    entity_id: UUID,
    data: RenameEntityIn,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> TreeEntityRead:
    entity = await tree_service.rename_entity(session, project.id, entity_id, data.name)
    return await _read(session, project.id, entity)


@router.patch(
    "/entities/{entity_id}/move",
    response_model=TreeEntityRead,
    summary="Move (reparent) a tree entity",
    responses=_ERRORS,
)
async def move_entity(
    entity_id: UUID,
    data: MoveEntityIn,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
) -> TreeEntityRead:
    entity = await tree_service.move_entity(session, project.id, entity_id, data.new_parent_id)
    return await _read(session, project.id, entity)


@router.delete(
    "/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tree entity (recursive for folders)",
    responses=_ERRORS,
)
async def delete_entity(
    entity_id: UUID,
    project: Project = Depends(owned_project),
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
) -> None:
    await tree_service.delete_entity(session, project.id, entity_id, store=store)
