"""File-tree request/response schemas (spec 12)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

TreeEntityTypeLiteral = Literal["folder", "doc", "file"]


class CreateEntityIn(BaseModel):
    # "file" entities are created by spec 14's upload, not here.
    type: Literal["folder", "doc"]
    name: str
    parent_id: UUID | None = None


class RenameEntityIn(BaseModel):
    name: str


class MoveEntityIn(BaseModel):
    new_parent_id: UUID


class TreeEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    parent_id: UUID | None
    type: TreeEntityTypeLiteral
    name: str
    is_root: bool
    created_at: datetime
    updated_at: datetime
    path: str


class TreeNode(TreeEntityRead):
    # Present (possibly empty) for folders; ``None`` for docs/files.
    children: list[TreeNode] | None = None


class TreeRead(BaseModel):
    root: TreeNode
