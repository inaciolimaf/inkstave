from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inkstave.modules.projects.models.project_import import ImportSource, ProjectImportStatus


class CompatFindingRead(BaseModel):
    """One line of the compatibility report (spec 120)."""

    rule_id: str
    severity: Literal["info", "warning"]
    path: str
    line: int
    message: str


class ProjectImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # Aliased from the row's ``id`` (mirrors how CompileStatusResponse maps a row).
    import_id: UUID = Field(validation_alias="id")
    project_id: UUID
    status: ProjectImportStatus
    source: ImportSource = ImportSource.ZIP
    compat_report: list[CompatFindingRead] | None = None
    report_seen_at: datetime | None = None
    entries_total: int | None = None
    entries_imported: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
