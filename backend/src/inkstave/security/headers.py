"""Secure response headers on every response, incl. errors/404 (spec 52 §5.2.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.datastructures import MutableHeaders

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from inkstave.config import Settings

_STATIC_HEADERS = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "geolocation=(), microphone=(), camera=()",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    """Add CSP/HSTS/frame/nosniff/referrer/permissions headers; strip server banners."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.csp = settings.csp_policy
        self.hsts_enabled = settings.hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _STATIC_HEADERS.items():
                    headers[name] = value
                headers["content-security-policy"] = self.csp
                if self.hsts_enabled:
                    headers["strict-transport-security"] = _HSTS
                # Don't advertise the framework/version.
                del headers["x-powered-by"]
                del headers["server"]
            await send(message)

        await self.app(scope, receive, send_wrapper)
