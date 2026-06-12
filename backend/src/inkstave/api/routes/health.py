"""Liveness and readiness probes.

These live at the application root (not under ``/api/v1``) so orchestration
probes stay version-independent. ``/health`` is always cheap; ``/ready`` checks
backing dependencies (currently just Redis) with a short timeout.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from inkstave.db.engine import check_db
from inkstave.redis_client import ping_redis

router = APIRouter(tags=["health"])

# Short bound on each readiness dependency check so the probe never hangs.
READY_TIMEOUT_SECONDS = 0.5


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Always-cheap liveness check; never touches Redis or the database."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request) -> Any:
    """Readiness check: ``200`` only when every dependency answers."""
    redis = getattr(request.app.state, "redis", None)
    redis_ok = bool(redis is not None and await ping_redis(redis, READY_TIMEOUT_SECONDS))

    db_engine = getattr(request.app.state, "db_engine", None)
    db_ok = bool(db_engine is not None and await check_db(db_engine, READY_TIMEOUT_SECONDS))

    checks = {
        "redis": "ok" if redis_ok else "error",
        "db": "ok" if db_ok else "error",
    }
    if redis_ok and db_ok:
        return {"status": "ready", "checks": checks}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": checks},
    )
