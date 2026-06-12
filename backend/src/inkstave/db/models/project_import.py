"""The ``project_imports`` table — async .zip-import job status/metadata (spec 101).

Mirrors the ``compiles`` table shape (spec 22) so the import status surface
(poll + SSE) is consistent with the compile one. One row tracks the lifecycle of
a single archive upload → new-project reconstruction.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from inkstave.db.models.project import Project


class ProjectImportStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"  # imported, but some entries were skipped
    FAILURE = "failure"  # a ZipImportError (zip-slip / bomb / invalid / …)
    ERROR = "error"  # an unexpected error (the job never crashes)


_TERMINAL = frozenset(
    {
        ProjectImportStatus.SUCCESS,
        ProjectImportStatus.PARTIAL,
        ProjectImportStatus.FAILURE,
        ProjectImportStatus.ERROR,
    }
)
_ACTIVE = frozenset({ProjectImportStatus.QUEUED, ProjectImportStatus.RUNNING})


def is_terminal(status: ProjectImportStatus) -> bool:
    return status in _TERMINAL


def is_active(status: ProjectImportStatus) -> bool:
    return status in _ACTIVE


class ProjectImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_imports"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProjectImportStatus.QUEUED
    )
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    entries_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entries_imported: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','success','partial','failure','error')",
            name="project_import_status_valid",
        ),
        CheckConstraint("source_bytes >= 0", name="project_import_source_bytes_nonneg"),
        Index("ix_project_imports_project_id", "project_id"),
        Index("ix_project_imports_requester", "requested_by", text("created_at DESC")),
    )
