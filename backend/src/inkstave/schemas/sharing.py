"""Schemas for collaborators & sharing (spec 33)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from inkstave.schemas.base import StrictModel

InviteRoleLiteral = Literal["editor", "viewer"]


class MemberRead(BaseModel):
    """A person with access to a project (owner or active member)."""

    user_id: UUID
    name: str
    email: str
    role: str
    status: str


class MemberRoleUpdate(StrictModel):
    # Plain str so an attempt to set 'owner' reaches the service and returns a
    # domain 400 (the transfer endpoint is the only path to owner) rather than 422.
    role: str


class TransferRequest(StrictModel):
    to_user_id: UUID


class InviteCreate(StrictModel):
    email: EmailStr
    role: InviteRoleLiteral


class InviteRead(BaseModel):
    """A pending invite as listed to the owner (no raw token)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class InviteCreated(InviteRead):
    """The create-invite response — carries the raw token back to the inviter only."""

    token: str


class InvitePreview(BaseModel):
    """Public-ish preview shown on the accept-invite screen."""

    project_id: UUID
    project_name: str
    inviter_name: str
    role: str
    email: str


class AcceptResponse(BaseModel):
    project_id: UUID
    role: str
