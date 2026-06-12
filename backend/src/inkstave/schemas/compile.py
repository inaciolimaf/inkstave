"""Compile API request/response schemas (spec 22)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompileRequest(BaseModel):
    main_file: str | None = None
    force: bool = False


class OutputSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    kind: str
    content_type: str
    size_bytes: int
    etag: str


class CompileStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: str
    main_file: str
    has_pdf: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    exit_code: int | None
    error_message: str | None
    log_excerpt: str | None = None
    artifact_manifest: list[dict[str, Any]] | None = None
