"""First-run setup endpoints (spec 57 §5.4) — mounted at ``/api/setup`` (NOT
versioned): a launchpad-style gate that creates the first admin once, then locks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.auth.password import PasswordHasher
from inkstave.bootstrap.admin import admin_exists, ensure_initial_admin
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_password_hasher
from inkstave.errors import ConflictError
from inkstave.schemas.base import StrictModel
from inkstave.schemas.user import RegisterRequest, UserPublic

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatus(StrictModel):
    needs_setup: bool


@router.get("/status", response_model=SetupStatus, summary="Whether a first admin is still needed")
async def setup_status(session: AsyncSession = Depends(get_db_session)) -> SetupStatus:
    return SetupStatus(needs_setup=not await admin_exists(session))


@router.post(
    "/admin",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create the first admin (locked once one exists)",
)
async def create_first_admin(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> UserPublic:
    admin = await ensure_initial_admin(
        session,
        hasher,
        email=data.email,
        password=data.password,
        display_name=data.display_name,
    )
    if admin is None:
        # Already set up — locked forever (409). Creates nothing.
        raise ConflictError("setup is locked: an admin already exists")
    return UserPublic.model_validate(admin)
