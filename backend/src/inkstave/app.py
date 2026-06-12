"""Application factory and lifespan.

``create_app()`` builds a fully configured FastAPI app with no network I/O at
construction time. Connections (Redis now; the DB engine in spec 03) are opened
in the async lifespan and disposed on shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from inkstave import __version__
from inkstave.api.router import api_v1
from inkstave.api.routes import health
from inkstave.config import Settings, get_settings
from inkstave.db.engine import check_db, create_engine_and_sessionmaker
from inkstave.errors import ErrorEnvelope
from inkstave.exception_handlers import register_exception_handlers
from inkstave.logging import configure_logging
from inkstave.middleware import RequestIdMiddleware
from inkstave.redis_client import create_redis_pool, ping_redis

logger = logging.getLogger("inkstave.app")

# Bound on the lifespan startup Redis ping (longer than the readiness probe;
# a failure only warns, it does not abort startup).
STARTUP_PING_TIMEOUT_SECONDS = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open shared connections on startup; dispose them on shutdown."""
    settings = get_settings()

    # --- Redis ---
    redis = await create_redis_pool(settings.redis_url)
    app.state.redis = redis
    app.state.db_engine = None
    app.state.db_sessionmaker = None

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
        else:
            logger.warning("DATABASE_URL is not configured; database is disabled")

        yield
    finally:
        await redis.aclose()
        app.state.redis = None
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

    app = FastAPI(
        title=settings.app_name + " API",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
    )

    # Middleware (outermost added last). Request-id wraps CORS so the access log
    # and correlation id cover preflight responses too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)

    register_exception_handlers(app)

    # Root-level probes (version-independent) + the versioned API router.
    app.include_router(health.router)
    app.include_router(api_v1)

    app.openapi = _build_openapi(app, settings)  # type: ignore[method-assign]

    return app
