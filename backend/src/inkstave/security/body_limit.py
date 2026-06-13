"""Global request-body size limit (spec 52 §5.2.2). Rejects oversize bodies early."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from starlette.datastructures import Headers

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from inkstave.config import Settings


def _too_large_response(limit: int) -> dict[str, object]:
    body = json.dumps(
        {
            "error": {
                "code": "payload_too_large",
                "message": f"Request body exceeds the {limit}-byte limit.",
            }
        }
    ).encode()
    return {"body": body, "length": len(body)}


class BodySizeLimitMiddleware:
    """Abort with 413 when Content-Length exceeds the cap, or while streaming past it.

    Binary-upload routes (``/files`` for blob uploads, ``/import`` for project zips)
    use the larger upload cap; everything else the JSON cap. The import route then
    enforces its own precise ``import_max_zip_bytes`` while streaming the body.
    """

    # Path suffixes that carry binary payloads, not JSON — exempt from the small
    # JSON cap so a legitimately large upload isn't rejected before the route can
    # apply its own (stricter, streamed) size guard.
    _UPLOAD_SUFFIXES = ("/files", "/import")

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.json_cap = settings.max_request_body_bytes
        self.upload_cap = settings.max_upload_bytes

    def _cap(self, path: str) -> int:
        stripped = path.rstrip("/")
        is_upload = any(stripped.endswith(suffix) for suffix in self._UPLOAD_SUFFIXES)
        return self.upload_cap if is_upload else self.json_cap

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cap = self._cap(scope["path"])
        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > cap:
                await self._reject(send, cap)
                return

        # Streamed body without (or under-declared) Content-Length: count and abort.
        received = 0
        too_large = False

        async def counting_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > cap:
                    too_large = True
            return message

        sent_413 = False

        async def guarded_send(message: Message) -> None:
            nonlocal sent_413
            if too_large and not sent_413:
                sent_413 = True
                await self._reject(send, cap)
                return
            if not sent_413:
                await send(message)

        await self.app(scope, counting_receive, guarded_send)

    async def _reject(self, send: Send, limit: int) -> None:
        payload = _too_large_response(limit)
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(payload["length"]).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload["body"]})
