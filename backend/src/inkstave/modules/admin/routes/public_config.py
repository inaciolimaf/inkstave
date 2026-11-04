"""Public configuration the frontend reads at start-up: the optional features this server runs (spec 121)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from inkstave.core.config.settings import Settings
from inkstave.core.deps import get_settings_dep

router = APIRouter(prefix="/config", tags=["config"])


class PublicConfig(BaseModel):
    git_enabled: bool


@router.get("", response_model=PublicConfig, summary="Optional features this server runs")
async def public_config(settings: Settings = Depends(get_settings_dep)) -> PublicConfig:
    return PublicConfig(git_enabled=settings.git_enabled)
