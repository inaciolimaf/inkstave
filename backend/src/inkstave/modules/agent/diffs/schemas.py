from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class DiffOutcomeIn(StrictModel):
    """The user's decision on each hunk of a proposal (spec 110). Ids are the ``hunk_id`` values."""

    accepted: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
