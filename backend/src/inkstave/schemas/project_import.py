"""Project-import API response schema (spec 101)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.db.models.project_import import ProjectImportStatus


class ProjectImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Aliased from the row's ``id`` (mirrors how CompileStatusResponse maps a row).
    import_id: UUID = Field(validation_alias="id")
    project_id: UUID
    status: ProjectImportStatus
    entries_total: int | None = None
    entries_imported: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
