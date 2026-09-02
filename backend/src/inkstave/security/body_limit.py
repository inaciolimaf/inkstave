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

    @staticmethod
    def _declared_over(scope: Scope, cap: int) -> bool:
        """True when the request declares a Content-Length above `cap`."""
        content_length = Headers(scope=scope).get("content-length")
        if content_length is None:
            return False
        try:
            return int(content_length) > cap
        except ValueError:
            return False

    def _guarded_pipe(self, receive: Receive, send: Send, cap: int) -> tuple[Receive, Send]:
        """A receive/send pair that aborts with 413 once `cap` bytes are exceeded.

        Handles a streamed body without (or with an under-declared) Content-Length:
        it counts what actually arrives and rejects before the route can answer.
        """
        state = {"received": 0, "too_large": False, "rejected": False}

        async def counting_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                state["too_large"] = state["received"] > cap
            return message

        async def guarded_send(message: Message) -> None:
            if state["rejected"]:
                return
            if state["too_large"]:
                state["rejected"] = True
                await self._reject(send, cap)
                return
            await send(message)

        return counting_receive, guarded_send

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cap = self._cap(scope["path"])
        if self._declared_over(scope, cap):
            await self._reject(send, cap)
            return

        counting_receive, guarded_send = self._guarded_pipe(receive, send, cap)
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
