"""User-facing schemas: registration request and public representation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# 72 is the historical bcrypt limit; kept as a stable, documented cap even though
# argon2 has no such limit.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72


class RegisterRequest(BaseModel):
    """Public registration payload with server-side strength rules."""

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Display name must not be empty.")
        return stripped

    @field_validator("password")
    @classmethod
    def _password_charset(cls, value: str) -> str:
        if not any(c.isalpha() for c in value):
            raise ValueError("Password must contain at least one letter.")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one digit.")
        return value

    @model_validator(mode="after")
    def _password_not_similar_to_email(self) -> RegisterRequest:
        local_part = self.email.split("@", 1)[0].lower()
        if local_part and local_part in self.password.lower():
            raise ValueError("Password must not contain your email address.")
        return self


class UserPublic(BaseModel):
    """Safe public representation of a user — never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    email_confirmed: bool
    created_at: datetime
