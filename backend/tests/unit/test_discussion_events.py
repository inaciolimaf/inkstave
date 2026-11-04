"""Unit tests for the project event stream's publish side and frames, and the chat body rules (spec 117)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from inkstave.modules.discussion.events.channel import (
    _publish_quietly,
    project_channel,
    publish_project_event,
)
from inkstave.modules.discussion.events.stream import _frame
from inkstave.modules.discussion.models import CHAT_BODY_MAX_LENGTH
from inkstave.modules.discussion.schemas import ChatMessageCreate


def test_channel_name_is_per_project() -> None:
    project = uuid4()
    assert project_channel(project) == f"project:events:{project}"


def test_frame_carries_id_event_and_json_data() -> None:
    frame = _frame({"type": "chat.message_deleted", "payload": {"id": "m1"}, "id": 7})
    assert frame == (
        b'id: 7\nevent: chat.message_deleted\ndata: {"type": "chat.message_deleted", '
        b'"payload": {"id": "m1"}, "id": 7}\n\n'
    )


async def test_publish_numbers_events_per_project_and_publishes_them(redis: Any) -> None:
    project = uuid4()
    pubsub = redis.pubsub()
    await pubsub.subscribe(project_channel(project))
    await pubsub.get_message(timeout=0.05)  # the subscribe confirmation

    first = await publish_project_event(redis, project, "chat.message_created", {"n": 1})
    second = await publish_project_event(redis, project, "chat.message_created", {"n": 2})
    assert (first, second) == (1, 2)

    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
    assert message is not None
    assert json.loads(message["data"]) == {"type": "chat.message_created", "payload": {"n": 1}, "id": 1}


async def test_publish_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenRedis:
        async def incr(self, *_args: object) -> int:
            raise ConnectionError("redis is down")

    await _publish_quietly(BrokenRedis(), uuid4(), "chat.message_created", {})  # type: ignore[arg-type]
    assert "project event publish failed" in caplog.text


def test_message_body_is_trimmed_and_must_have_text() -> None:
    assert ChatMessageCreate(body="  Oi \n").body == "Oi"
    with pytest.raises(ValidationError):
        ChatMessageCreate(body=" \t\n ")
    with pytest.raises(ValidationError):
        ChatMessageCreate(body="x" * (CHAT_BODY_MAX_LENGTH + 1))
