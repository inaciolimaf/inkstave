"""Admin-gated routes. Spec 08 adds only a ping to exercise ``require_admin``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from inkstave.auth.dependencies import require_admin
from inkstave.db.models.user import User
from inkstave.errors import ErrorEnvelope

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/ping",
    summary="Admin-only liveness ping (guards proof)",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
        status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    },
)
async def admin_ping(_: User = Depends(require_admin)) -> dict[str, bool]:
    return {"ok": True}
