"""What a comment write produces besides its row: the event to publish and the e-mails to send (spec 118).

The service returns one of these; the route publishes and enqueues only after the commit, so a
failed commit sends nothing (see ``publish.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Notification excerpts and mail quotes are cut to this many characters.
EXCERPT_MAX_CHARS = 140


@dataclass(frozen=True)
class MentionMail:
    """One ``comment_mention`` e-mail, sent through the mailer job."""

    to: str
    context: dict[str, Any]


@dataclass(frozen=True)
class CommentOutcome[T]:
    result: T
    # Event type and JSON payload; None when the write changed nothing and needs no event.
    event: tuple[str, dict[str, Any]] | None = None
    mails: tuple[MentionMail, ...] = ()


def excerpt(body: str) -> str:
    """The first part of a message, for a notification or an e-mail."""
    if len(body) <= EXCERPT_MAX_CHARS:
        return body
    return body[: EXCERPT_MAX_CHARS - 1] + "…"
