"""History API schemas (spec 37)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.schemas.base import StrictModel


class AuthorInfo(BaseModel):
    id: UUID
    name: str
    email: str


class LabelBrief(BaseModel):
    id: UUID
    name: str


class VersionEntry(BaseModel):
    version: int
    timestamp: datetime
    author: AuthorInfo | None
    op_count: int
    size: int
    labels: list[LabelBrief]


class VersionsResponse(BaseModel):
    doc_id: UUID
    current_version: int
    versions: list[VersionEntry]
    has_more: bool
    next_before: int | None


class UpdateEntry(BaseModel):
    version: int
    timestamp: datetime
    author: AuthorInfo | None
    op_count: int
    size: int


class UpdatesResponse(BaseModel):
    doc_id: UUID
    updates: list[UpdateEntry]


class DiffSegment(BaseModel):
    type: str
    value: str


class DiffHunk(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    segments: list[DiffSegment]


class DiffResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: int = Field(alias="from")
    to: int | str
    binary: bool = False
    too_large: bool = False
    hunks: list[DiffHunk]


class LabelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int
    doc_id: UUID | None
    created_by: UUID | None
    created_at: datetime


class LabelCreate(StrictModel):
    version: int
    name: str = Field(min_length=1, max_length=255)


class ProjectLabelCreate(StrictModel):
    name: str = Field(min_length=1, max_length=255)


class RestoreRequest(StrictModel):
    version: int
    label_name: str | None = Field(default=None, min_length=1, max_length=255)


class RestoreResponse(BaseModel):
    doc_id: UUID
    restored_from_version: int
    new_version: int
    label: LabelRead | None


class ProjectRestoreRequest(StrictModel):
    label_id: UUID


class DocRestoreResult(BaseModel):
    doc_id: UUID
    status: str
    new_version: int | None = None
    reason: str | None = None


class ProjectRestoreResponse(BaseModel):
    results: list[DocRestoreResult]
