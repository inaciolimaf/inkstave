"""Pure helpers that derive paths and assemble the nested tree (spec 12).

Split out from :mod:`inkstave.services.tree_service` for file-size hygiene; the
service module re-exports these so existing import paths keep working.
"""

from __future__ import annotations

from collections import defaultdict
from typing import cast
from uuid import UUID

from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.schemas.tree import TreeEntityTypeLiteral, TreeNode, TreeRead
from inkstave.services.tree_errors import EntityNotFoundError


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
