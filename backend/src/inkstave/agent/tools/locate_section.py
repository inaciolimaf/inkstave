"""locate_section tool (spec 42, structure-aware as of spec 48)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from inkstave.agent.context import build_project_map
from inkstave.agent.context import locate_section as resolve_sections
from inkstave.agent.tools._common import load_tree
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import read_content_for_collab


class LocateSectionArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    doc_id: str | None = None


class LocateSectionTool(Tool):
    name = "locate_section"
    description = "Find a LaTeX section/chapter by human name and return its line range."
    Args = LocateSectionArgs

    async def run(self, args: LocateSectionArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)

        entities, paths = await load_tree(ctx)
        id_by_path: dict[str, str] = {paths[e.id]: str(e.id) for e in entities}

        # Pre-read every text document so the project map's file_reader is synchronous.
        contents: dict[str, str] = {}
        for entity in entities:
            if entity.type == TreeEntityType.doc:
                contents[paths[entity.id]] = await read_content_for_collab(ctx.db, entity.id)

        target_path: str | None = None
        if args.doc_id is not None:
            try:
                target_path = paths.get(UUID(args.doc_id))
            except (ValueError, AttributeError):
                target_path = None
            if target_path is None:
                return ToolResult.failure("not_found", "No such document in this project.")

        extra = [
            c.strip() for c in ctx.settings.agent_section_extra_commands.split(",") if c.strip()
        ]
        project_map = build_project_map(
            str(ctx.project_uuid),
            list(contents),
            contents.get,
            extra_commands=extra,
            cache=ctx.settings.agent_context_cache,
        )

        matches = resolve_sections(project_map, args.name)
        result = [
            {
                "doc_id": id_by_path.get(m.node.file_path),
                "path": m.node.file_path,
                "level": m.node.command,
                "title": m.node.title,
                "heading_line": m.node.start_line,
                "start_line": m.node.start_line,
                "end_line": m.node.end_line,
                # Character offsets (spec 48 §5.2): callers need the char range,
                # not just line numbers, to map a section onto file content.
                "start_char": m.node.start_char,
                "end_char": m.node.end_char,
                "char_range": [m.node.start_char, m.node.end_char],
                "score": m.score,
            }
            for m in matches
            if target_path is None or m.node.file_path == target_path
        ]
        # The method label was upgraded from spec-42's "heuristic-v1" to the
        # structure-aware "structure-v1" in spec 48 (see ADR-0048). The label is
        # kept as "structure-v1" deliberately; it is not a behaviour change.
        return ToolResult.success(matches=result, method="structure-v1")
