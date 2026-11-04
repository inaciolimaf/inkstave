from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.core.schemas import StrictModel


class HunkLine(BaseModel):
    op: Literal[" ", "-", "+"]
    text: str


class Hunk(BaseModel):
    hunk_id: str
    header: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[HunkLine]
    additions: int
    deletions: int


class DiffStats(BaseModel):
    additions: int
    deletions: int
    hunk_count: int


class ProposedDiffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    message_id: UUID | None
    project_id: UUID
    doc_id: UUID
    path: str
    base_version: str
    base_hash: str
    diff_text: str
    hunks: list[Hunk]
    stats: DiffStats
    status: str
    rationale: str | None
    created_at: datetime


class DiffOutcomeIn(StrictModel):
    """The user's decision on each hunk of a proposal (spec 110). Ids are the ``hunk_id`` values."""

    accepted: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
