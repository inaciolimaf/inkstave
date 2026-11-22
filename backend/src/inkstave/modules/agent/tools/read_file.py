"""read_file tool (spec 42): read a text document's current content."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from inkstave.modules.agent.tools._common import (
    edits_for,
    load_tree,
    resolve_document,
    text_after_staged_edits,
)
from inkstave.modules.agent.tools.base import Tool, ToolContext, ToolResult, authorize
from inkstave.modules.projects import TreeEntity, TreeEntityType


class ReadFileArgs(BaseModel):
    doc_id: str | None = None
    path: str | None = None
    start_line: int | None = Field(default=None, ge=0)
    end_line: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_selector(self) -> ReadFileArgs:
        if (self.doc_id is None) == (self.path is None):
            raise ValueError("provide exactly one of doc_id or path")
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
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


_DESCRIPTION = (
    "Read a text document. `content` is the exact text, with no line numbers: copy old_text for "
    "propose_edit from it verbatim. Optional 0-based [start_line, end_line) window. Read a document "
    "before proposing an edit to it."
)


class ReadFileTool(Tool):
    name = "read_file"
    description = _DESCRIPTION
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

        # Remember what the model read: propose_edit only works on a document read in this turn.
        ctx.read_versions[doc_id] = str(document.version)
        # Show the text the turn's staged edits leave, so old_text can match the next edit.
        lines = text_after_staged_edits(ctx, doc_id, document.content).splitlines(keepends=True)
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
            **_notes(ctx, doc_id, truncated),
        }
        return ToolResult.success(**result)


def _notes(ctx: ToolContext, doc_id: str, truncated: bool) -> dict[str, object]:
    """Optional result fields: the turn's earlier edits in this document, and a truncation hint."""
    notes: dict[str, object] = {}
    count = len(edits_for(ctx, doc_id))
    if count:
        notes["proposed_edits"] = count
        notes["note"] = "content already includes the edits proposed earlier in this turn"
    if truncated:
        notes["hint"] = "Output exceeds the size cap; request a smaller line range."
    return notes


def _doc_id_for_path(entities: list[TreeEntity], paths: dict[UUID, str], path: str | None) -> str | None:
    """The id of the document at `path`, or ``None`` when there is none."""
    target = next((e for e in entities if paths[e.id] == path and e.type == TreeEntityType.doc), None)
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
