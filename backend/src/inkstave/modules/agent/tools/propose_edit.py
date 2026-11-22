"""propose_edit tool (spec 42): stage an exact-text replacement (never applies, never diffs).

The model names the text to change (``old_text``) and what replaces it (``new_text``). The
tool refuses unless the document was read in this turn and has not changed since, and
``old_text`` must occur exactly once in the text the turn's earlier edits leave behind.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from inkstave.modules.agent.graph.edits import StagedEdit
from inkstave.modules.agent.tools._common import resolve_document, text_after_staged_edits
from inkstave.modules.agent.tools.base import Tool, ToolContext, ToolResult, authorize


class ProposeEditArgs(BaseModel):
    doc_id: str
    old_text: str = Field(
        description=(
            "The exact text to replace, copied verbatim from read_file's content. It must occur exactly "
            "once in the file: use a short snippet that is unique, or include surrounding lines. Empty "
            "only for an empty file."
        )
    )
    new_text: str = Field(description="What replaces old_text. Use an empty string to delete old_text.")
    rationale: str | None = Field(default=None, max_length=500)


class ProposeEditTool(Tool):
    name = "propose_edit"
    description = (
        "Propose replacing old_text with new_text in one document, for the user to review. Does not apply "
        "it. Call read_file on the document first and copy old_text exactly from its content. One call per "
        "place changed: several edits to one file are several calls."
    )
    Args = ProposeEditArgs

    async def run(self, args: ProposeEditArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx, require_write=True)) is not None:
            return ToolResult(ok=False, error=denied)

        limit = ctx.settings.agent_tool_edit_max_chars
        if len(args.new_text) > limit or len(args.old_text) > limit:
            return ToolResult.failure(
                "invalid_args", f"old_text and new_text must each be at most {limit} chars."
            )

        resolved = await resolve_document(ctx, args.doc_id)
        if not isinstance(resolved, tuple):
            return ToolResult(ok=False, error=resolved)
        _entity, document, path = resolved

        if (refused := _read_guard(ctx, args.doc_id, str(document.version))) is not None:
            return refused
        text = text_after_staged_edits(ctx, args.doc_id, document.content)
        if (refused := _match_error(args, text)) is not None:
            return refused

        staged = _stage(args, path, str(document.version))
        ctx.staged_edits.append(staged)  # consumed at the end of the turn; the document is NOT changed
        return ToolResult.success(
            edit_id=staged.edit_id,
            doc_id=args.doc_id,
            path=path,
            base_version=staged.base_version,
            staged=True,
        )


def _read_guard(ctx: ToolContext, doc_id: str, version: str) -> ToolResult | None:
    """Refuse unless this turn read the document and it has not changed since."""
    read_version = ctx.read_versions.get(doc_id)
    if read_version is None:
        return ToolResult.failure("invalid_args", "read_file this document before proposing an edit.")
    if read_version != version:
        return ToolResult.failure("invalid_args", "the file changed since you read it; read_file again.")
    return None


def _match_error(args: ProposeEditArgs, text: str) -> ToolResult | None:
    """Refuse an ``old_text`` that does not match ``text`` exactly once."""
    if args.old_text == "":
        if text == "":
            return None
        return ToolResult.failure(
            "invalid_args",
            "old_text is empty; it may be empty only for an empty file. Copy the text to replace.",
        )
    if args.old_text == args.new_text:
        return ToolResult.failure(
            "invalid_args", "new_text is the same as old_text; there is nothing to change."
        )
    found = text.count(args.old_text)
    if found == 0:
        return ToolResult.failure(
            "invalid_args", "old_text not found in the current file; read_file again and copy the exact text."
        )
    if found > 1:
        return ToolResult.failure(
            "invalid_args",
            f"old_text occurs {found} times in the file; include more surrounding context so it occurs once.",
        )
    return None


def _stage(args: ProposeEditArgs, path: str, base_version: str) -> StagedEdit:
    return StagedEdit(
        edit_id=uuid.uuid4().hex,
        doc_id=args.doc_id,
        path=path,
        base_version=base_version,
        old_text=args.old_text,
        new_text=args.new_text,
        rationale=args.rationale,
    )
