"""read_file tool (spec 42): read a text document's current content."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from inkstave.agent.tools._common import load_tree, resolve_document
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType


class ReadFileArgs(BaseModel):
    doc_id: str | None = None
    path: str | None = None
    start_line: int | None = Field(default=None, ge=0)
    end_line: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_selector(self) -> ReadFileArgs:
        if (self.doc_id is None) == (self.path is None):
            raise ValueError("provide exactly one of doc_id or path")
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must be >= start_line")
        return self


def _cap_to_chars(lines: list[str], cap: int) -> tuple[str, int, bool]:
    """Keep whole lines whose cumulative length stays within ``cap``.

    Returns (text, lines_kept, truncated). A single line longer than the cap is
    hard-truncated so output is never empty when there is content.
    """
    kept: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) > cap:
            break
        kept.append(line)
        size += len(line)
    truncated = len(kept) < len(lines)
    if not kept and lines:  # first line alone exceeds the cap
        return lines[0][:cap], 1, True
    return "".join(kept), len(kept), truncated


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a text document's content (optionally a 0-based [start,end) line window)."
    Args = ReadFileArgs

    async def run(self, args: ReadFileArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx)) is not None:
            return ToolResult(ok=False, error=denied)

        entities, paths = await load_tree(ctx)
        doc_id = args.doc_id or _doc_id_for_path(entities, paths, args.path)
        if doc_id is None:
            return ToolResult.failure("not_found", "No such document in this project.")

        resolved = await resolve_document(ctx, doc_id, paths)
        if not isinstance(resolved, tuple):
            return ToolResult(ok=False, error=resolved)
        _entity, document, path = resolved

        lines = document.content.splitlines(keepends=True)
        window = _window(args, lines)
        if window is None:
            return ToolResult.failure("invalid_args", "start_line is past end of document.")
        start, selected = window

        # The char cap applies on BOTH paths (a wide window must not pull the whole doc).
        text, kept, truncated = _cap_to_chars(selected, ctx.settings.agent_tool_read_max_chars)
        result: dict[str, object] = {
            "doc_id": doc_id,
            "path": path,
            "version": str(document.version),
            "start_line": start,
            "end_line": start + kept,
            "line_count": len(lines),
            "content": text,
            "truncated": truncated,
        }
        if truncated:
            result["hint"] = "Output exceeds the size cap; request a smaller line range."
        return ToolResult.success(**result)


def _doc_id_for_path(
    entities: list[TreeEntity], paths: dict[UUID, str], path: str | None
) -> str | None:
    """The id of the document at `path`, or ``None`` when there is none."""
    target = next(
        (e for e in entities if paths[e.id] == path and e.type == TreeEntityType.doc), None
    )
    return None if target is None else str(target.id)


def _window(args: ReadFileArgs, lines: list[str]) -> tuple[int, list[str]] | None:
    """The requested ``[start, end)`` slice, or ``None`` when start is past the end."""
    if args.start_line is None and args.end_line is None:
        return 0, lines
    start = args.start_line or 0
    if start > len(lines):
        return None
    end = args.end_line if args.end_line is not None else len(lines)
    return start, lines[start:end]
