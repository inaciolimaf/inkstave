"""Typed errors of the discussion module (spec 117)."""

from __future__ import annotations

from inkstave.core.errors import ForbiddenError, NotFoundError


class ChatMessageNotFoundError(NotFoundError):
    error_type = "chat_message_not_found"

    def __init__(self) -> None:
        super().__init__("Chat message not found.")


class NotMessageAuthorError(ForbiddenError):
    error_type = "not_message_author"

    def __init__(self) -> None:
        super().__init__("Only the author can delete this message.")
