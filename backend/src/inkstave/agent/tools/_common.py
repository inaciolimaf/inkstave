"""Shared tree/document resolution helpers for the tools (spec 42)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.agent.tools.base import ToolContext, ToolError
from inkstave.db.models.document import Document
from inkstave.db.models.tree_entity import TreeEntity
from inkstave.services.document_service import NotADocumentError, get_document
from inkstave.services.tree_service import EntityNotFoundError, compute_path, get_tree

if TYPE_CHECKING:
    pass


async def load_tree(ctx: ToolContext) -> tuple[list[TreeEntity], dict[UUID, str]]:
    """All entities in the session's project + each entity's full path."""
    entities = await get_tree(ctx.db, ctx.project_uuid)
    by_id = {e.id: e for e in entities}
    paths = {e.id: compute_path(e, by_id) for e in entities}
    return entities, paths


def depth_of(entity: TreeEntity, by_id: dict[UUID, TreeEntity]) -> int:
    """Hops from the project root (root = 0)."""
    depth = 0
    current: TreeEntity | None = entity
    while current is not None and current.parent_id is not None:
        depth += 1
        current = by_id.get(current.parent_id)
    return depth


async def resolve_document(
    ctx: ToolContext, doc_id_str: str, paths: dict[UUID, str] | None = None
) -> tuple[TreeEntity, Document, str] | ToolError:
    """Resolve a doc id within the project → (entity, document, path) or a ToolError.

    A bad/foreign id yields ``not_found`` (no cross-project leak); a non-text target
    yields ``unsupported``. ``get_document`` already enforces both, so the entity is a
    text document — we fetch it from the tree (not ``document.entity``, which would
    trigger an async lazy-load).
    """
    try:
        doc_id = UUID(doc_id_str)
    except (ValueError, AttributeError):
        return ToolError(code="not_found", message="No such document in this project.")
    try:
        document = await get_document(ctx.db, ctx.project_uuid, doc_id)
    except EntityNotFoundError:
        return ToolError(code="not_found", message="No such document in this project.")
    except NotADocumentError:
        return ToolError(code="unsupported", message="That file is not a text document.")

    entities, computed_paths = await load_tree(ctx)
    entity = next((e for e in entities if e.id == doc_id), None)
    if entity is None:  # resolved as a document but absent from the tree — treat as missing
        return ToolError(code="not_found", message="No such document in this project.")
    path = (paths or computed_paths).get(doc_id, entity.name)
    return entity, document, path
