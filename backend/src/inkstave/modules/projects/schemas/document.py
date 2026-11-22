from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.core.schemas import StrictModel


class DocumentContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: UUID
    project_id: UUID
    version: int
    size_bytes: int
    content: str
    updated_at: datetime


class DocumentContentReplace(StrictModel):
    # Stored byte-for-byte: leading and trailing whitespace is part of a LaTeX document, so the
    # schema's str_strip_whitespace (on for every other request body) is switched off here.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    content: str
    # The version the client edited from; must match the server's current version.
    base_version: int = Field(ge=0)
