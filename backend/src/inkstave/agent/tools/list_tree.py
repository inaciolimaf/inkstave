"""list_tree tool (spec 42): enumerate the project file tree."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from inkstave.agent.tools._common import depth_of, load_tree
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType


class ListTreeArgs(BaseModel):
    path: str | None = Field(default=None, description="Subtree root path; default = root.")
    depth: int = Field(default=3, ge=1, le=10)


async def _size_index(ctx: ToolContext, entity_ids: list[UUID]) -> dict[UUID, int]:
    """Byte sizes for doc/file nodes (optional per spec 42 §5.2.5); folders omit it."""
    sizes: dict[UUID, int] = {}
    for model in (Document, File):
        rows = await ctx.db.execute(
            select(model.entity_id, model.size_bytes).where(model.entity_id.in_(entity_ids))
        )
        for entity_id, size_bytes in rows:
            sizes[entity_id] = size_bytes
    return sizes


def _in_subtree(path: str, root_path: str) -> bool:
    return not root_path or path == root_path or path.startswith(root_path + "/")


def _wanted(entity: TreeEntity, path: str, rel_depth: int, root_path: str, max_depth: int) -> bool:
    """True for a non-root node inside the requested subtree and depth window."""
    if entity.is_root or not _in_subtree(path, root_path):
        return False
    return 1 <= rel_depth <= max_depth


def _root_scope(
    args: ListTreeArgs,
    entities: list[TreeEntity],
    paths: dict[UUID, str],
    by_id: dict[UUID, TreeEntity],
) -> tuple[int, str] | None:
    """Depth + path of the requested subtree root; ``None`` when the path is unknown."""
    if args.path is None:
        return 0, ""
    target = next((e for e in entities if paths[e.id] == args.path), None)
    if target is None:
        return None
    return depth_of(target, by_id), args.path


def _node(entity: TreeEntity, path: str, sizes: dict[UUID, int]) -> dict[str, object]:
    return {
        "node_id": str(entity.id),
        "path": path,
        "type": entity.type.value,
        "size": sizes.get(entity.id),  # None for folders (optional field)
        "is_binary": entity.type == TreeEntityType.file,
    }


class ListTreeTool(Tool):
    name = "list_tree"
    description = "List the project's file tree (folders, documents, files) under a path."
    Args = ListTreeArgs

    async def run(self, args: ListTreeArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)

        entities, paths = await load_tree(ctx)
        by_id = {e.id: e for e in entities}
        sizes = await _size_index(ctx, [e.id for e in entities])

        scope = _root_scope(args, entities, paths, by_id)
        if scope is None:
            return ToolResult.failure("not_found", "No such path in this project.")
        root_depth, root_path = scope

        max_nodes = ctx.settings.agent_tool_tree_max_nodes
        nodes: list[dict[str, object]] = []
        truncated = False
        for entity in entities:
            rel = depth_of(entity, by_id) - root_depth
            if not _wanted(entity, paths[entity.id], rel, root_path, args.depth):
                continue
            if len(nodes) >= max_nodes:
                truncated = True
                break
            nodes.append(_node(entity, paths[entity.id], sizes))

        return ToolResult.success(nodes=nodes, truncated=truncated)
