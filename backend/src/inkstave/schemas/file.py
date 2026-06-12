"""Binary file metadata schema (spec 14)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    project_id: UUID
    name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    original_filename: str | None
    created_at: datetime
    updated_at: datetime
