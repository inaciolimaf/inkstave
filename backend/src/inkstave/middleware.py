"""Request-id middleware and per-request access logging.

Implemented as pure ASGI (rather than ``BaseHTTPMiddleware``) so the request-id
``ContextVar`` set here remains visible to downstream endpoints, exception
handlers and the access log without task-isolation surprises.
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders

from inkstave.logging import set_request_id

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

access_logger = logging.getLogger("inkstave.access")


class RequestIdMiddleware:
    """Assign/propagate a correlation id and emit one access-log line per request."""

    def __init__(self, app: ASGIApp, header_name: str) -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(self.header_name) or uuid4().hex
        # Overwrite every request so a stale value never leaks between requests.
        set_request_id(request_id)

        status_code = 500
        start = perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[self.header_name] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            access_logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
