"""search_project tool (spec 42): keyword search over text docs + paths."""

from __future__ import annotations

import fnmatch

from pydantic import BaseModel, Field

from inkstave.agent.tools._common import load_tree
from inkstave.agent.tools._latex import scan_headings
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import read_content_for_collab

_SNIPPET_MAX = 240
_PAYLOAD_SOFT_CAP = 8192
# Rank: section titles, then content lines, then path-only matches.
_KIND_RANK = {"section": 0, "content": 1, "path": 2}


class SearchProjectArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    max_results: int = Field(default=20, ge=1, le=50)
    path_glob: str | None = None


class SearchProjectTool(Tool):
    name = "search_project"
    description = "Search the project's text documents and paths for a keyword."
    Args = SearchProjectArgs

    async def run(self, args: SearchProjectArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)

        query = args.query.strip()
        if not query:
            return ToolResult.failure("invalid_args", "query must not be empty")
        needle = query.lower()
        cap = min(args.max_results, ctx.settings.agent_tool_search_max_results)

        entities, paths = await load_tree(ctx)
        docs = [
            (e, paths[e.id])
            for e in entities
            if e.type == TreeEntityType.doc
            and (args.path_glob is None or fnmatch.fnmatch(paths[e.id], args.path_glob))
        ]

        matches: list[dict[str, object]] = []
        for entity, path in docs:
            if needle in path.lower():
                matches.append({"doc_id": str(entity.id), "path": path, "line": 0,
                                "snippet": path[:_SNIPPET_MAX], "kind": "path"})
            content = await read_content_for_collab(ctx.db, entity.id)
            section_lines = {h.line for h in scan_headings(content) if needle in h.title.lower()}
            for i, line in enumerate(content.splitlines()):
                if needle in line.lower():
                    kind = "section" if i in section_lines else "content"
                    matches.append({"doc_id": str(entity.id), "path": path, "line": i,
                                    "snippet": line.strip()[:_SNIPPET_MAX], "kind": kind})

        matches.sort(key=lambda m: _KIND_RANK.get(str(m["kind"]), 9))
        truncated = len(matches) > cap
        matches = matches[:cap]

        # Soft payload cap: drop trailing matches if the snippets get too big.
        size = 0
        bounded: list[dict[str, object]] = []
        for match in matches:
            size += len(str(match["snippet"])) + 64
            if size > _PAYLOAD_SOFT_CAP:
                truncated = True
                break
            bounded.append(match)

        return ToolResult.success(matches=bounded, truncated=truncated)
