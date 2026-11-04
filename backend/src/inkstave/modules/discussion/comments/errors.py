"""Typed errors of comment threads (spec 118). The author-only rule reuses ``NotMessageAuthorError``."""

from __future__ import annotations

from inkstave.core.errors import AppError, NotFoundError


class CommentThreadNotFoundError(NotFoundError):
    error_type = "comment_thread_not_found"

    def __init__(self) -> None:
        super().__init__("Comment thread not found.")


class CommentMessageNotFoundError(NotFoundError):
    error_type = "comment_message_not_found"

    def __init__(self) -> None:
        super().__init__("Comment message not found.")


class NotATextDocumentError(AppError):
    status_code = 422
    error_type = "not_a_text_document"

    def __init__(self) -> None:
        super().__init__("Comments can only be added to a text document.")
