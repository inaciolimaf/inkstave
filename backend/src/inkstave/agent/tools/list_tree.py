"""list_tree tool (spec 42): enumerate the project file tree."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from inkstave.agent.tools._common import depth_of, load_tree
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.tree_entity import TreeEntityType


class ListTreeArgs(BaseModel):
    path: str | None = Field(default=None, description="Subtree root path; default = root.")
    depth: int = Field(default=3, ge=1, le=10)


class ListTreeTool(Tool):
    name = "list_tree"
    description = "List the project's file tree (folders, documents, files) under a path."
    Args = ListTreeArgs

    async def run(self, args: ListTreeArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)

        entities, paths = await load_tree(ctx)
        by_id = {e.id: e for e in entities}

        # Byte sizes for doc/file nodes (optional per spec 42 §5.2.5); folders omit it.
        sizes: dict[UUID, int] = {}
        for entity_id, size_bytes in await ctx.db.execute(
            select(Document.entity_id, Document.size_bytes).where(
                Document.entity_id.in_([e.id for e in entities])
            )
        ):
            sizes[entity_id] = size_bytes
        for entity_id, size_bytes in await ctx.db.execute(
            select(File.entity_id, File.size_bytes).where(
                File.entity_id.in_([e.id for e in entities])
            )
        ):
            sizes[entity_id] = size_bytes

        root_depth = 0
        if args.path is not None:
            target = next((e for e in entities if paths[e.id] == args.path), None)
            if target is None:
                return ToolResult.failure("not_found", "No such path in this project.")
            root_depth = depth_of(target, by_id)
            root_path = args.path
        else:
            root_path = ""

        max_nodes = ctx.settings.agent_tool_tree_max_nodes
        nodes: list[dict[str, object]] = []
        truncated = False
        for entity in entities:
            if entity.is_root:
                continue
            path = paths[entity.id]
            if root_path and not (path == root_path or path.startswith(root_path + "/")):
                continue
            rel = depth_of(entity, by_id) - root_depth
            if rel < 1 or rel > args.depth:
                continue
            if len(nodes) >= max_nodes:
                truncated = True
                break
            nodes.append(
                {
                    "node_id": str(entity.id),
                    "path": path,
                    "type": entity.type.value,
                    "size": sizes.get(entity.id),  # None for folders (optional field)
                    "is_binary": entity.type == TreeEntityType.file,
                }
            )

        return ToolResult.success(nodes=nodes, truncated=truncated)
