"""HTTP schemas for the agent API (spec 44)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.schemas.base import StrictModel


class AgentSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    title: str | None
    status: str
    model: str
    run_state: str
    active_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seq: int
    role: str
    content: str | None
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None
    token_usage: dict[str, Any] | None
    created_at: datetime


class ProposedDiffSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doc_id: UUID
    path: str
    base_version: str
    stats: dict[str, Any]
    status: str
    rationale: str | None
    created_at: datetime
    hunks: list[dict[str, Any]] | None = None


class SessionDetailOut(BaseModel):
    session: AgentSessionOut
    messages: list[AgentMessageOut]
    diffs: list[ProposedDiffSummary]


class PostMessageIn(StrictModel):
    content: str = Field(min_length=1)


class PostMessageOut(BaseModel):
    run_id: UUID
    stream_url: str


class CreateSessionIn(StrictModel):
    title: str | None = Field(default=None, max_length=200)
