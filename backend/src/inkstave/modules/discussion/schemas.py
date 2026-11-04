"""Request and response models of the project chat (spec 117)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inkstave.modules.discussion.models import CHAT_BODY_MAX_LENGTH

if TYPE_CHECKING:
    from inkstave.modules.discussion.models import ProjectChatMessage


class ChatAuthor(BaseModel):
    id: UUID
    display_name: str


class ChatMessageRead(BaseModel):
    """One message. A deleted message keeps its place with ``deleted`` set and no body."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    body: str | None
    author: ChatAuthor | None
    created_at: datetime
    deleted: bool

    @classmethod
    def from_message(cls, message: ProjectChatMessage, author: ChatAuthor | None) -> ChatMessageRead:
        deleted = message.deleted_at is not None
        return cls(
            id=message.id,
            body=None if deleted else message.body,
            author=author,
            created_at=message.created_at,
            deleted=deleted,
        )


class ChatMessagePage(BaseModel):
    """A page of messages, newest first. ``has_more`` says whether older ones exist."""

    items: list[ChatMessageRead]
    has_more: bool


class ChatMessageCreate(BaseModel):
    body: str = Field(description="Plain text, trimmed; up to 4000 characters after trimming")

    @field_validator("body")
    @classmethod
    def _trimmed_and_bounded(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message cannot be blank.")
        if len(stripped) > CHAT_BODY_MAX_LENGTH:
            raise ValueError(f"Message is longer than {CHAT_BODY_MAX_LENGTH} characters.")
        return stripped


class UnreadCount(BaseModel):
    count: int
