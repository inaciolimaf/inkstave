"""User-facing schemas: registration request and public representation."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from inkstave.schemas.base import StrictModel

# 72 is the historical bcrypt limit; kept as a stable, documented cap even though
# argon2 has no such limit.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72

PasswordStr = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]


def validate_password_charset(value: str) -> str:
    """The spec-06 strength rule: at least one letter and one digit."""
    if not any(c.isalpha() for c in value):
        raise ValueError("Password must contain at least one letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one digit.")
    return value


class RegisterRequest(StrictModel):
    """Public registration payload with server-side strength rules."""

    email: EmailStr
    password: PasswordStr
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
        return validate_password_charset(value)

    @model_validator(mode="after")
    def _password_not_similar_to_email(self) -> RegisterRequest:
        local_part = self.email.split("@", 1)[0].lower()
        if local_part and local_part in self.password.lower():
            raise ValueError("Password must not contain your email address.")
        return self


# --- Editor preferences (spec 59) -------------------------------------------- #

EditorTheme = Literal["light", "dark", "system"]
EditorKeymap = Literal["default", "vim", "emacs"]
FONT_SIZE_MIN = 10
FONT_SIZE_MAX = 28


class EditorPreferences(StrictModel):
    """Per-user editor settings; server clamps font size and enums the rest."""

    theme: EditorTheme = "system"
    font_size: int = 14
    keymap: EditorKeymap = "default"

    @field_validator("font_size")
    @classmethod
    def _clamp_font_size(cls, value: int) -> int:
        return max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, value))


class UserPublic(BaseModel):
    """Safe public representation of a user — never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    email_confirmed: bool
    created_at: datetime


class UserMe(UserPublic):
    """The signed-in user's own view, including profile + preferences (spec 59).

    NOTE (spec 68 #22): ``GET /api/v1/users/me`` returns this model — a strict
    superset of the spec-08 ``UserPublic`` (adds ``avatar_url``,
    ``editor_preferences``, ``pending_email``). This is intentional over-delivery
    introduced by spec 59; the extra fields never break a ``UserPublic`` consumer.
    """

    avatar_url: str | None = None
    editor_preferences: EditorPreferences = EditorPreferences()
    pending_email: str | None = None


# --- Settings requests (spec 59) --------------------------------------------- #


class UpdateProfileRequest(StrictModel):
    """Patch the profile; both fields optional (at least one should be sent)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = Field(default=None, max_length=2000)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Display name must not be empty.")
        return stripped


class ChangePasswordRequest(StrictModel):
    current_password: str
    new_password: PasswordStr

    @field_validator("new_password")
    @classmethod
    def _charset(cls, value: str) -> str:
        return validate_password_charset(value)


class ChangeEmailRequest(StrictModel):
    new_email: EmailStr
    current_password: str


class ConfirmEmailChangeRequest(StrictModel):
    token: str = Field(min_length=1, max_length=512)


class DeleteAccountRequest(StrictModel):
    password: str
    confirm: bool = False

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Deletion must be explicitly confirmed.")
        return value
