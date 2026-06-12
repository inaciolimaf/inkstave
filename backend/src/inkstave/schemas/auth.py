"""Authentication request/response schemas (spec 07)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr

from inkstave.schemas.base import StrictModel


class LoginRequest(StrictModel):
    email: EmailStr
    password: str


class RefreshRequest(StrictModel):
    refresh_token: str


class LogoutRequest(StrictModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    detail: str
