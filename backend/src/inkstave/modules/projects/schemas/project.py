from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inkstave.core.schemas import StrictModel
from inkstave.modules.projects.models.membership import MembershipRole

NAME_MAX_LENGTH = 255

SpellcheckLanguage = Literal["off", "en-US", "pt-BR"]


def _validate_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Project name must not be blank.")
    return stripped


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    # The client sends the creator's interface language (spec 113); en-US when omitted.
    spellcheck_language: SpellcheckLanguage = "en-US"

    _trim_name = field_validator("name")(_validate_name)


class ProjectSettingsUpdate(StrictModel):
    """Project settings a document writer may change (spec 113)."""

    spellcheck_language: SpellcheckLanguage


class ProjectRename(StrictModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)

    _trim_name = field_validator("name")(_validate_name)


class ProjectRead(BaseModel):
    """Public project representation — ``deleted_at`` is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    root_doc_id: UUID | None
    # Defaulted so cached rows written before spec 113 still validate.
    spellcheck_language: SpellcheckLanguage = "en-US"
    created_at: datetime
    updated_at: datetime


class ProjectList(BaseModel):
    items: list[ProjectRead]
    total: int


class PermissionsRead(BaseModel):
    """The caller's effective role + capability codes on a project (spec 34)."""

    role: MembershipRole
    capabilities: list[str]
