"""propose_edit tool (spec 42): stage an edit intent (never applies, never diffs)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator

from inkstave.agent.edits import EditMode, StagedEdit
from inkstave.agent.tools._common import resolve_document
from inkstave.agent.tools.base import Tool, ToolContext, ToolResult, authorize


class ProposeEditArgs(BaseModel):
    doc_id: str
    mode: EditMode
    new_text: str
    start_line: int | None = Field(default=None, ge=0)
    end_line: int | None = Field(default=None, ge=0)
    rationale: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _range_fields(self) -> ProposeEditArgs:
        if self.mode == EditMode.range and (self.start_line is None or self.end_line is None):
            raise ValueError("range mode requires start_line and end_line")
        return self


class ProposeEditTool(Tool):
    name = "propose_edit"
    description = (
        "Stage a proposed change to a document for the user to review. Does not apply it."
    )
    Args = ProposeEditArgs

    async def run(self, args: ProposeEditArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx, require_write=True)) is not None:
            return ToolResult(ok=False, error=denied)

        if len(args.new_text) > ctx.settings.agent_tool_edit_max_chars:
            return ToolResult.failure("invalid_args", "new_text exceeds the maximum size.")

        resolved = await resolve_document(ctx, args.doc_id)
        if not isinstance(resolved, tuple):
            return ToolResult(ok=False, error=resolved)
        _entity, document, path = resolved

        if args.mode == EditMode.range:
            line_count = len(document.content.splitlines())
            start, end = args.start_line, args.end_line
            assert start is not None and end is not None  # guaranteed by the validator
            if start > end or end > line_count:
                return ToolResult.failure(
                    "invalid_args", "range is outside the document's bounds."
                )

        base_version = str(document.version)
        staged = StagedEdit(
            edit_id=uuid.uuid4().hex,
            doc_id=args.doc_id,
            path=path,
            base_version=base_version,
            mode=args.mode,
            new_text=args.new_text,
            start_line=args.start_line,
            end_line=args.end_line,
            rationale=args.rationale,
        )
        ctx.staged_edits.append(staged)  # consumed by spec 43; the document is NOT changed
        return ToolResult.success(
            edit_id=staged.edit_id,
            doc_id=args.doc_id,
            path=path,
            mode=args.mode.value,
            base_version=base_version,
            staged=True,
        )
