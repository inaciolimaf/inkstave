"""Document content request/response schemas (spec 13)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    project_id: UUID
    version: int
    size_bytes: int
    content: str
    updated_at: datetime


class DocumentContentReplace(BaseModel):
    content: str
    # The version the client edited from; must match the server's current version.
    base_version: int = Field(ge=0)
