"""File-tree request/response schemas (spec 12)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.schemas.base import StrictModel
from inkstave.services.safe_path import MAX_TREE_ENTITY_NAME_LENGTH

TreeEntityTypeLiteral = Literal["folder", "doc", "file"]


class CreateEntityIn(StrictModel):
    # "file" entities are created by spec 14's upload, not here.
    type: Literal["folder", "doc"]
    # Fail-fast length guard (spec 100); validate_name_segment still enforces the
    # character/reserved-name rules the service-layer check covers.
    name: str = Field(min_length=1, max_length=MAX_TREE_ENTITY_NAME_LENGTH)
    parent_id: UUID | None = None


class RenameEntityIn(StrictModel):
    name: str = Field(min_length=1, max_length=MAX_TREE_ENTITY_NAME_LENGTH)


class MoveEntityIn(StrictModel):
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
