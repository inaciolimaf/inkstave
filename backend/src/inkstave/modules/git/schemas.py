"""Request and response models for the Git access token routes (spec 121 §5.1)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GitTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="A label for the token, such as the machine.")
    expires_at: datetime | None = Field(default=None, description="Optional expiry, in the future.")

    @field_validator("name")
    @classmethod
    def _strip_and_require(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A token needs a name.")
        return cleaned

    @field_validator("expires_at")
    @classmethod
    def _in_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("The expiry must be in the future.")
        return value


class GitTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    prefix: str = Field(description="The first characters of the token, to tell tokens apart.")
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class GitTokenCreated(GitTokenRead):
    token: str = Field(description="The token itself. It is shown once and cannot be retrieved again.")


class GitTokenList(BaseModel):
    tokens: list[GitTokenRead]
