"""Optional OpenTelemetry tracing (spec 51 §5.4). Off by default; lazily imported.

When OTEL_ENABLED is false (default, and always in tests) NOTHING from
``opentelemetry`` is imported, so the dependency is optional and tests pay nothing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from inkstave.config import Settings

logger = logging.getLogger("inkstave.observability.tracing")

_enabled = False


def current_trace_id() -> str | None:
    """Hex trace id of the active span when tracing is on; otherwise None."""
    if not _enabled:
        return None
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:  # never let tracing break a request
        return None
    return None


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Initialize tracing only when OTEL_ENABLED=true (no-op + no imports otherwise)."""
    global _enabled
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import (  # type: ignore[import-not-found]
            FastAPIInstrumentor,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
        )

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        _enabled = True
        logger.info("OpenTelemetry tracing enabled")
    except Exception:
        logger.exception("failed to initialize OpenTelemetry; continuing without tracing")
