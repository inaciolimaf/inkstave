"""File-tree proposals: create, delete, move. Each one stages, and none of them applies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from inkstave.modules.agent.file_ops.paths import ancestors_of, normalize_path, subtree_paths
from inkstave.modules.agent.graph.edits import FileOpKind, StagedFileOp
from inkstave.modules.agent.tools._common import load_tree
from inkstave.modules.agent.tools.base import Tool, ToolContext, ToolError, ToolResult, authorize
from inkstave.modules.projects import InvalidNameError, TreeEntityType, validate_name_segment

if TYPE_CHECKING:
    from inkstave.modules.projects import TreeEntity

_Rationale = Field(default=None, max_length=500)


class _Tree:
    """The project's tree as one proposal sees it, keyed by path."""

    def __init__(self, entities: list[TreeEntity], paths: dict[UUID, str]) -> None:
        self.by_path = {paths[e.id]: e for e in entities if not e.is_root}
        self.by_lower = {path.lower(): e for path, e in self.by_path.items()}


async def _load(ctx: ToolContext) -> _Tree:
    return _Tree(*await load_tree(ctx))


def _invalid(message: str) -> ToolError:
    return ToolError(code="invalid_args", message=message)


def _bad_name(path: str) -> ToolError | None:
    """The first segment the tree would refuse, as an error the model can act on."""
    if not path:
        return _invalid("The path must name something below the project root.")
    try:
        for segment in path.split("/"):
            validate_name_segment(segment)
    except InvalidNameError as exc:
        return _invalid(str(exc))
    return None


def _target_problem(tree: _Tree, path: str, *, own_path: str | None = None) -> ToolError | None:
    """Why nothing can be placed at ``path``. ``own_path`` is what is moving there, if anything."""
    if (bad := _bad_name(path)) is not None:
        return bad
    taken = tree.by_lower.get(path.lower())
    if taken is not None and path.lower() != (own_path or "").lower():
        return _invalid(f"{path} already exists.")
    for folder in ancestors_of(path):
        found = tree.by_lower.get(folder.lower())
        if found is not None and found.type is not TreeEntityType.folder:
            return _invalid(f"{folder} is a file, not a folder.")
    return None


def _already_staged(ctx: ToolContext, *paths: str) -> ToolError | None:
    """Two proposals in a turn must not touch one path: the user could apply only one."""
    wanted = {p.lower() for p in paths}
    for staged in ctx.staged_file_ops:
        if wanted & {staged.path.lower(), (staged.new_path or "").lower()}:
            return _invalid(f"This turn already proposed a change to {staged.path}.")
    return None


def _stage(ctx: ToolContext, op: StagedFileOp) -> ToolResult:
    ctx.staged_file_ops.append(op)
    return ToolResult.success(
        kind=op.kind.value, path=op.path, new_path=op.new_path, staged=True, applied=False
    )


class ProposeCreateArgs(BaseModel):
    path: str = Field(min_length=1, description="Project-relative path; missing folders are created too.")
    type: Literal["doc", "folder"] = "doc"
    content: str = Field(default="", description="The whole text of a new document.")
    rationale: str | None = _Rationale

    @model_validator(mode="after")
    def _folders_are_empty(self) -> ProposeCreateArgs:
        if self.type == "folder" and self.content:
            raise ValueError("a folder has no content")
        return self


class ProposeCreateTool(Tool):
    name = "propose_create"
    description = (
        "Propose a new text document or folder. The user decides; nothing exists until then, "
        "so give a new document its whole content here."
    )
    Args = ProposeCreateArgs

    async def run(self, args: ProposeCreateArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx, require_write=True)) is not None:
            return ToolResult(ok=False, error=denied)
        if len(args.content) > ctx.settings.agent_tool_edit_max_chars:
            return ToolResult.failure("invalid_args", "content exceeds the maximum size.")
        path = normalize_path(args.path)
        problem = _target_problem(await _load(ctx), path) or _already_staged(ctx, path)
        if problem is not None:
            return ToolResult(ok=False, error=problem)
        content = args.content if args.type == "doc" else None
        op = StagedFileOp(
            kind=FileOpKind.create,
            entity_type=args.type,
            path=path,
            content=content,
            rationale=args.rationale,
        )
        return _stage(ctx, op)


class ProposeDeleteArgs(BaseModel):
    path: str = Field(min_length=1, description="Document, file or folder; a folder goes with its contents.")
    rationale: str | None = _Rationale


class ProposeDeleteTool(Tool):
    name = "propose_delete"
    description = "Propose deleting a document, file or folder. The user decides; deleting cannot be undone."
    Args = ProposeDeleteArgs

    async def run(self, args: ProposeDeleteArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx, require_write=True)) is not None:
            return ToolResult(ok=False, error=denied)
        path = normalize_path(args.path)
        tree = await _load(ctx)
        entity = tree.by_path.get(path)
        if entity is None:
            return ToolResult.failure("not_found", "No such path in this project.")
        if (problem := _already_staged(ctx, path)) is not None:
            return ToolResult(ok=False, error=problem)
        op = StagedFileOp(
            kind=FileOpKind.delete,
            entity_id=entity.id,
            entity_type=entity.type.value,
            path=path,
            affected_paths=subtree_paths(tree.by_path, path),
            rationale=args.rationale,
        )
        return _stage(ctx, op)


class ProposeMoveArgs(BaseModel):
    path: str = Field(min_length=1)
    new_path: str = Field(min_length=1, description="Full new path: covers a rename, a move, or both.")
    rationale: str | None = _Rationale


def _move_problem(tree: _Tree, path: str, new_path: str) -> ToolError | None:
    if new_path == path:
        return _invalid("new_path is the same as path.")
    if new_path.lower().startswith(f"{path.lower()}/"):
        return _invalid("A folder cannot move into itself.")
    return _target_problem(tree, new_path, own_path=path)


class ProposeMoveTool(Tool):
    name = "propose_move"
    description = "Propose renaming or moving a document, file or folder. The user decides."
    Args = ProposeMoveArgs

    async def run(self, args: ProposeMoveArgs, ctx: ToolContext) -> ToolResult:  # type: ignore[override]
        if (denied := await authorize(ctx, require_write=True)) is not None:
            return ToolResult(ok=False, error=denied)
        path, new_path = normalize_path(args.path), normalize_path(args.new_path)
        tree = await _load(ctx)
        entity = tree.by_path.get(path)
        if entity is None:
            return ToolResult.failure("not_found", "No such path in this project.")
        problem = _move_problem(tree, path, new_path) or _already_staged(ctx, path, new_path)
        if problem is not None:
            return ToolResult(ok=False, error=problem)
        op = StagedFileOp(
            kind=FileOpKind.move,
            entity_id=entity.id,
            entity_type=entity.type.value,
            path=path,
            new_path=new_path,
            rationale=args.rationale,
        )
        return _stage(ctx, op)
