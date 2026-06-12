"""The ``compiles`` table — async compile job status/metadata (spec 22)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from inkstave.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from inkstave.db.models.project import Project


class CompileJobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


_TERMINAL = frozenset(
    {
        CompileJobStatus.SUCCESS,
        CompileJobStatus.FAILURE,
        CompileJobStatus.TIMEOUT,
        CompileJobStatus.CANCELLED,
        CompileJobStatus.ERROR,
    }
)
_ACTIVE = frozenset({CompileJobStatus.QUEUED, CompileJobStatus.RUNNING})


def is_terminal(status: CompileJobStatus) -> bool:
    return status in _TERMINAL


def is_active(status: CompileJobStatus) -> bool:
    return status in _ACTIVE


class Compile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compiles"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CompileJobStatus.QUEUED)
    main_file: Mapped[str] = mapped_column(Text, nullable=False)
    job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_manifest: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    has_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship()

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','success','failure','timeout','cancelled','error')",
            name="compile_status_valid",
        ),
        Index("ix_compiles_project_created", "project_id", "created_at"),
        Index("ix_compiles_job_id", "job_id"),
        Index("ix_compiles_status", "status"),
        Index("ix_compiles_requested_by", "requested_by"),
    )
