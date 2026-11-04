"""Request and response models of comment threads (spec 118)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inkstave.modules.discussion.comments.anchors import ANCHOR_MAX_B64_CHARS, decode_anchor
from inkstave.modules.discussion.comments.models import COMMENT_BODY_MAX_LENGTH, QUOTE_MAX_CHARS
from inkstave.modules.discussion.schemas import ChatAuthor


def _trimmed_body(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Message cannot be blank.")
    if len(stripped) > COMMENT_BODY_MAX_LENGTH:
        raise ValueError(f"Message is longer than {COMMENT_BODY_MAX_LENGTH} characters.")
    return stripped


def _check_anchor(value: str) -> str:
    decode_anchor(value)  # raises ValueError, which the request model reports as a 422
    return value


class CommentMessageRead(BaseModel):
    """One message. A deleted message keeps its place with ``deleted`` set and no body."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    body: str | None
    author: ChatAuthor | None
    mentions: list[UUID]
    created_at: datetime
    edited_at: datetime | None
    deleted: bool


class CommentThreadRead(BaseModel):
    id: UUID
    document_id: UUID
    anchor_start: str = Field(description="Base64 of the Yjs relative position of the start")
    anchor_end: str = Field(description="Base64 of the Yjs relative position of the end")
    quoted_text: str
    author: ChatAuthor | None
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: ChatAuthor | None
    messages: list[CommentMessageRead]


class CommentThreadList(BaseModel):
    items: list[CommentThreadRead]


class CommentThreadCreate(BaseModel):
    document_id: UUID
    anchor_start: str = Field(max_length=ANCHOR_MAX_B64_CHARS)
    anchor_end: str = Field(max_length=ANCHOR_MAX_B64_CHARS)
    quoted_text: str = Field(min_length=1, max_length=QUOTE_MAX_CHARS)
    body: str = Field(description="Plain text, trimmed; up to 4000 characters after trimming")
    mentions: list[UUID] = Field(default_factory=list, description="Ids the body mentions")

    @field_validator("anchor_start", "anchor_end")
    @classmethod
    def _anchor_decodes(cls, value: str) -> str:
        return _check_anchor(value)

    @field_validator("body")
    @classmethod
    def _body_bounded(cls, value: str) -> str:
        return _trimmed_body(value)


class CommentMessageWrite(BaseModel):
    """A reply, or the new text of an edited message."""

    body: str
    mentions: list[UUID] = Field(default_factory=list, description="Ids the body mentions")

    @field_validator("body")
    @classmethod
    def _body_bounded(cls, value: str) -> str:
        return _trimmed_body(value)
