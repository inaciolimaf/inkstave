"""Authentication request/response schemas (spec 07)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from inkstave.schemas.base import StrictModel


class LoginRequest(StrictModel):
    email: EmailStr
    password: str


class RefreshRequest(StrictModel):
    refresh_token: str


class LogoutRequest(StrictModel):
    refresh_token: str


class ForgotPasswordRequest(StrictModel):
    email: EmailStr


# Email link-based auth flows (spec 104).
class EmailOnlyRequest(StrictModel):
    """Request body for verify-email/resend and magic-link (email only)."""

    email: EmailStr


class TokenOnlyRequest(StrictModel):
    """Request body for verify-email/confirm and magic-link/callback."""

    token: str = Field(min_length=1, max_length=512)


class ResetPasswordRequest(StrictModel):
    """Request body for reset-password (token authorizes; service re-validates strength)."""

    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=72)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    detail: str
