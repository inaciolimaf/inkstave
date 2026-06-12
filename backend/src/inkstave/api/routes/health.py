"""Liveness and readiness probes.

These live at the application root (not under ``/api/v1``) so orchestration
probes stay version-independent. ``/health`` is always cheap; ``/ready`` checks
backing dependencies (currently just Redis) with a short timeout.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from inkstave.config import get_settings
from inkstave.db.engine import check_db
from inkstave.observability import metrics
from inkstave.redis_client import ping_redis

logger = logging.getLogger("inkstave.health")

router = APIRouter(tags=["health"])

# Short bound on each readiness dependency check so the probe never hangs.
READY_TIMEOUT_SECONDS = 0.5


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Always-cheap liveness check; never touches Redis or the database."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request) -> Any:
    """Readiness check (spec 02 §5.2): Redis-only.

    Spec 02 scopes readiness to Redis (no DB exists yet at that point), so this
    probe answers ``200`` with ``{"status":"ready","checks":{"redis":"ok"}}``
    when Redis is reachable and ``503`` otherwise. The DB-aware readiness probe
    is ``/readyz`` (spec 51); do not add a DB check here.
    """
    redis = getattr(request.app.state, "redis", None)
    redis_ok = bool(redis is not None and await ping_redis(redis, READY_TIMEOUT_SECONDS))

    checks = {"redis": "ok" if redis_ok else "error"}
    if redis_ok:
        return {"status": "ready", "checks": checks}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": checks},
    )


@router.get("/healthz", summary="Liveness probe (spec 51)")
async def healthz() -> dict[str, str]:
    """Liveness: 200 as long as the process is up; never touches deps."""
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe (spec 51)")
async def readyz(request: Request) -> Any:
    """Readiness: 200 when DB + Redis answer within the per-check timeout, else 503."""
    timeout = get_settings().readiness_check_timeout_s
    redis = getattr(request.app.state, "redis", None)
    redis_ok = bool(redis is not None and await ping_redis(redis, timeout))
    db_engine = getattr(request.app.state, "db_engine", None)
    db_ok = bool(db_engine is not None and await check_db(db_engine, timeout))

    checks = {"db": "ok" if db_ok else "error", "redis": "ok" if redis_ok else "error"}
    if db_ok and redis_ok:
        return {"status": "ready", "checks": checks}
    logger.warning("readiness check failed: %s", checks)
    return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """Prometheus text exposition. Queue depth is sampled here, failing soft."""
    if not get_settings().metrics_public:
        return Response(status_code=404)
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        await metrics.sample_queue_depth(redis)
    return Response(content=metrics.render_latest(), media_type=metrics.CONTENT_TYPE)
