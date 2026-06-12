"""Application factory and lifespan.

``create_app()`` builds a fully configured FastAPI app with no network I/O at
construction time. Connections (Redis now; the DB engine in spec 03) are opened
in the async lifespan and disposed on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from inkstave import __version__
from inkstave.api.router import api_v1
from inkstave.api.routes import health, setup
from inkstave.collab.ws import router as collab_ws
from inkstave.collab.ws.components import build_collab_components
from inkstave.config import Settings, get_settings
from inkstave.db.engine import check_db, create_engine_and_sessionmaker
from inkstave.errors import ErrorEnvelope
from inkstave.exception_handlers import register_exception_handlers
from inkstave.observability.log import configure_logging
from inkstave.observability.metrics import set_build_info
from inkstave.observability.middleware import RequestContextMiddleware
from inkstave.observability.tracing import setup_tracing
from inkstave.redis_client import create_redis_pool, ping_redis
from inkstave.security.body_limit import BodySizeLimitMiddleware
from inkstave.security.headers import SecurityHeadersMiddleware

logger = logging.getLogger("inkstave.app")

# Bound on the lifespan startup Redis ping (longer than the readiness probe;
# a failure only warns, it does not abort startup).
STARTUP_PING_TIMEOUT_SECONDS = 2.0


async def _ensure_migrations(engine: Any, settings: Settings) -> None:
    """Migration gate (spec 57).

    Convenience mode (``MIGRATE_ON_START=true``) applies the advisory-locked
    upgrade now. Strict mode (the production default) refuses to start unless the
    DB is already at head — migrations belong to the one-shot ``migrate`` step.
    """
    from inkstave.bootstrap.migrate import is_database_at_head, run_upgrade

    if settings.migrate_on_start:
        await asyncio.to_thread(run_upgrade, settings)
        logger.info("Migrations applied at startup (MIGRATE_ON_START=true)")
        return
    if not await is_database_at_head(engine):
        raise RuntimeError(
            "Database is not at the latest migration (head). Run `inkstave migrate` "
            "first, or set MIGRATE_ON_START=true. Refusing to start."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared connections on startup; dispose them on shutdown."""
    settings = get_settings()

    # --- Redis ---
    redis = await create_redis_pool(settings.redis_url)
    app.state.redis = redis
    app.state.db_engine = None
    app.state.db_sessionmaker = None
    app.state.collab = None

    # Everything created above is disposed in the finally block, so a failure
    # while wiring the database below cannot leak the Redis pool.
    try:
        if await ping_redis(redis, STARTUP_PING_TIMEOUT_SECONDS):
            logger.info("Connected to Redis")
        else:
            # Do not crash: the app must still serve /health; /ready reports this.
            logger.warning("Redis ping failed at startup; continuing")

        # --- Database (async SQLAlchemy engine + sessionmaker) ---
        if settings.database_url:
            engine, sessionmaker = create_engine_and_sessionmaker(settings)
            app.state.db_engine = engine
            app.state.db_sessionmaker = sessionmaker
            if await check_db(engine, STARTUP_PING_TIMEOUT_SECONDS):
                logger.info("Connected to the database")
            else:
                logger.warning("Database check failed at startup; continuing")
            # Migration gate (spec 57): refuse to start unless the DB is at head,
            # or apply migrations now in convenience mode.
            await _ensure_migrations(engine, settings)
            # --- Collaboration (CRDT WebSocket) components (spec 28/29) ---
            app.state.collab = build_collab_components(
                redis=redis,
                session_factory=sessionmaker,
                settings=settings,
                instance_id=uuid4().hex,
            )
        else:
            logger.warning("DATABASE_URL is not configured; database is disabled")

        yield
    finally:
        # Flush any buffered history to the DB *before* tearing down the engine,
        # so un-debounced edits are not lost on shutdown (spec 40).
        collab = app.state.collab
        if collab is not None and collab.history is not None:
            try:
                await collab.history.flush_all()
            except Exception:  # never let a flush failure block clean shutdown
                logger.exception("history flush_all failed during shutdown")
        if collab is not None:
            # Cancel the manager's debounced flush/evict tasks before disposing the
            # engine, so none can wake up against a closed connection (spec 55).
            with suppress(Exception):
                await collab.manager.aclose()
        await redis.aclose()
        app.state.redis = None
        app.state.collab = None
        if app.state.db_engine is not None:
            await app.state.db_engine.dispose()
            app.state.db_engine = None
            app.state.db_sessionmaker = None


def _build_openapi(app: FastAPI, settings: Settings) -> Any:
    """Custom OpenAPI that documents the error envelope as a reusable component."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=settings.app_name + " API",
            version=__version__,
            description="Inkstave backend API.",
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        env_schema = ErrorEnvelope.model_json_schema(ref_template="#/components/schemas/{model}")
        components.update(env_schema.pop("$defs", {}))
        components["ErrorEnvelope"] = env_schema
        app.openapi_schema = schema
        return schema

    return openapi


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application."""
    settings = get_settings()
    configure_logging(settings)
    set_build_info(settings.app_version, settings.git_sha)

    app = FastAPI(
        title=settings.app_name + " API",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
    )

    # Middleware (outermost added LAST). Spec-52 order, outermost → inner:
    # RequestContext → SecurityHeaders → BodySizeLimit → CORS → routing.
    #
    # CORS deviation (supersedes spec 02 §5.2): spec 02 specified
    # ``allow_methods=["*"]`` / ``allow_headers=["*"]``. We deliberately tighten
    # to explicit allow-lists for defense-in-depth — only the methods and request
    # headers the API actually accepts are advertised in preflight responses.
    # This is intentional and stricter; do not loosen back to wildcards.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", settings.request_id_header],
        expose_headers=[settings.request_id_header, "X-RateLimit-Remaining", "Retry-After"],
    )
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware, header_name=settings.request_id_header)

    setup_tracing(app, settings)  # no-op unless OTEL_ENABLED=true
    register_exception_handlers(app)

    # Root-level probes (version-independent) + the versioned API router.
    app.include_router(health.router)
    # First-run setup lives at /api/setup (NOT versioned — spec 57).
    app.include_router(setup.router)
    app.include_router(api_v1)
    # Collaboration WebSocket lives at the root (not under /api/v1).
    app.include_router(collab_ws.router)

    app.openapi = _build_openapi(app, settings)  # type: ignore[method-assign]

    return app
