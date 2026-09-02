"""locate_section tool (spec 42, structure-aware as of spec 48)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from inkstave.agent.context import build_project_map
from inkstave.agent.context import locate_section as resolve_sections
from inkstave.agent.context.models import SectionMatch
from inkstave.agent.tools._common import load_tree
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
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
        contents = await _read_documents(ctx, entities, paths)

        target_path: str | None = None
        if args.doc_id is not None:
            target_path = _path_for_doc(args.doc_id, paths)
            if target_path is None:
                return ToolResult.failure("not_found", "No such document in this project.")

        project_map = build_project_map(
            str(ctx.project_uuid),
            list(contents),
            contents.get,
            extra_commands=_extra_commands(ctx),
            cache=ctx.settings.agent_context_cache,
        )
        matches = [
            _match_payload(m, id_by_path)
            for m in resolve_sections(project_map, args.name)
            if target_path is None or m.node.file_path == target_path
        ]
        # The method label was upgraded from spec-42's "heuristic-v1" to the
        # structure-aware "structure-v1" in spec 48 (see ADR-0048). The label is
        # kept as "structure-v1" deliberately; it is not a behaviour change.
        return ToolResult.success(matches=matches, method="structure-v1")


async def _read_documents(
    ctx: ToolContext, entities: list[TreeEntity], paths: dict[UUID, str]
) -> dict[str, str]:
    """Pre-read every text document so the project map's file_reader is synchronous."""
    contents: dict[str, str] = {}
    for entity in entities:
        if entity.type == TreeEntityType.doc:
            contents[paths[entity.id]] = await read_content_for_collab(ctx.db, entity.id)
    return contents


def _path_for_doc(doc_id: str, paths: dict[UUID, str]) -> str | None:
    """The project-relative path of `doc_id`, or ``None`` if it is not in this project."""
    try:
        return paths.get(UUID(doc_id))
    except (ValueError, AttributeError):
        return None


def _extra_commands(ctx: ToolContext) -> list[str]:
    return [c.strip() for c in ctx.settings.agent_section_extra_commands.split(",") if c.strip()]


def _match_payload(match: SectionMatch, id_by_path: dict[str, str]) -> dict[str, object]:
    node = match.node
    return {
        "doc_id": id_by_path.get(node.file_path),
        "path": node.file_path,
        "level": node.command,
        "title": node.title,
        "heading_line": node.start_line,
        "start_line": node.start_line,
        "end_line": node.end_line,
        # Character offsets (spec 48 §5.2): callers need the char range, not just
        # line numbers, to map a section onto file content.
        "start_char": node.start_char,
        "end_char": node.end_char,
        "char_range": [node.start_char, node.end_char],
        "score": match.score,
    }
