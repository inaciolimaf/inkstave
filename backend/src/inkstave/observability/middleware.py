"""Outermost HTTP middleware: request context, finish log, metrics (spec 51 §5.2.3)."""

from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.routing import Match

from inkstave.observability import metrics
from inkstave.observability.context import bind_context, clear_context
from inkstave.observability.tracing import current_trace_id

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("inkstave.access")

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
# Probe/scrape endpoints are excluded from access logs and request metrics (scrape noise).
_EXCLUDED_PATHS = {"/metrics", "/healthz", "/readyz", "/health", "/ready"}
_UNMATCHED = "<unmatched>"


def _route_path(route: object, scope: Scope) -> tuple[Match, str] | None:
    """How `route` matches `scope`, with its path template — ``None`` if unusable."""
    try:
        match, _ = route.matches(scope)  # type: ignore[attr-defined]
    except Exception:
        # A route whose matcher raises must never break request logging; skip it,
        # but leave a trace so a broken route definition is diagnosable.
        logger.debug("route matcher raised for %r", route, exc_info=True)
        return None
    path = getattr(route, "path", None)
    return (match, path) if isinstance(path, str) else None


def _route_template(scope: Scope) -> str:
    """The matched route's path template (bounded cardinality), or `<unmatched>`.

    Starlette doesn't persist the matched route on the outer scope, so match the
    request against the app's (flattened) routes and return the best match's template.
    """
    app = scope.get("app")
    if app is None:
        return _UNMATCHED
    partial: str | None = None
    for route in app.routes:
        found = _route_path(route, scope)
        if found is None:
            continue
        match, path = found
        if match == Match.FULL:
            return path
        if match == Match.PARTIAL and partial is None:
            partial = path  # path matched but method didn't (e.g. a 405)
    return partial if partial is not None else _UNMATCHED


class RequestContextMiddleware:
    """Bind correlation context, emit one finish log + HTTP metrics per request."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    def _request_id(self, scope: Scope) -> str:
        """The inbound correlation id when it is well-formed, else a fresh one."""
        inbound = Headers(scope=scope).get(self.header_name)
        return inbound if inbound and _VALID_REQUEST_ID.match(inbound) else uuid4().hex

    def _record(
        self, scope: Scope, status_code: int, duration_s: float, error: BaseException | None
    ) -> None:
        """Emit the finish log + HTTP metrics, unless the path is excluded."""
        template = _route_template(scope)
        method = scope["method"]
        if template in _EXCLUDED_PATHS or scope["path"] in _EXCLUDED_PATHS:
            return
        metrics.observe_http(method, template, status_code, duration_s)
        extra = {
            "http.method": method,
            "http.path": template,
            "http.status_code": status_code,
            "http.duration_ms": round(duration_s * 1000, 2),
        }
        if error is None:
            logger.info("request", extra=extra)
            return
        logger.error(
            "request failed",
            exc_info=(type(error), error, error.__traceback__),
            extra={**extra, "error.type": type(error).__name__},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        tokens = bind_context(request_id=request_id, trace_id=current_trace_id() or request_id)
        status_code = 500
        start = perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[self.header_name] = request_id
            await send(message)

        error: BaseException | None = None
        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException as exc:  # broad on purpose: re-raised to the spec-02 handlers
            error = exc
            raise
        finally:
            self._record(scope, status_code, perf_counter() - start, error)
            clear_context(tokens)
