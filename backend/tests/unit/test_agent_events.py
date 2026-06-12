"""Unit tests for the agent event bus + SSE forwarding (spec 44)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from inkstave.agent.api.events import (
    InMemoryEventSink,
    RedisEventSink,
    is_cancel_requested,
    last_event_key,
    request_cancel,
    run_channel,
)
from inkstave.agent.api.stream import sse_stream

pytestmark = pytest.mark.integration  # uses the fake redis fixture


def test_in_memory_sink_shape_and_seq() -> None:
    import asyncio

    sink = InMemoryEventSink("r1")

    async def go() -> None:
        await sink.emit("token", text="hi")
        await sink.emit("done", final_text="hi")

    asyncio.run(go())
    assert [e["type"] for e in sink.events] == ["token", "done"]
    assert [e["seq"] for e in sink.events] == [0, 1]
    assert sink.events[0]["run_id"] == "r1" and sink.events[0]["text"] == "hi"
    assert "ts" in sink.events[0]


async def test_redis_sink_publishes_and_persists_terminal(redis: Any) -> None:
    run_id = str(uuid4())
    pubsub = redis.pubsub()
    await pubsub.subscribe(run_channel(run_id))
    sink = RedisEventSink(redis, run_id, ttl_seconds=60)

    await sink.emit("token", text="x")
    await sink.emit("done", final_text="x")

    # Terminal event is persisted for late subscribers.
    raw = await redis.get(last_event_key(run_id))
    assert json.loads(raw)["type"] == "done"
    await pubsub.unsubscribe(run_channel(run_id))
    await pubsub.aclose()


async def test_cancel_flag_roundtrip(redis: Any) -> None:
    run_id = str(uuid4())
    assert await is_cancel_requested(redis, run_id) is False
    await request_cancel(redis, run_id, ttl_seconds=60)
    assert await is_cancel_requested(redis, run_id) is True


async def test_sse_replays_terminal_for_late_subscriber(redis: Any) -> None:
    # AC8: subscribing after the run finished still yields the terminal event.
    run_id = str(uuid4())
    sink = RedisEventSink(redis, run_id, ttl_seconds=60)
    await sink.emit("done", final_text="done")  # sets the last-event key

    frames = [frame async for frame in sse_stream(redis, run_id, heartbeat_seconds=1)]
    assert len(frames) == 1
    assert b"event: done" in frames[0]


async def test_sse_forwards_unknown_event_type_without_error(redis: Any) -> None:
    # Spec 44 §8: event-protocol forward-compat. An unknown (future) event type
    # must be forwarded as-is without error and must NOT be treated as terminal —
    # only "done"/"error" close the stream; surrounding known events still parse.
    import asyncio

    run_id = str(uuid4())
    collected: list[bytes] = []

    async def consume() -> None:
        async for frame in sse_stream(redis, run_id, heartbeat_seconds=5):
            collected.append(frame)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the subscriber attach
    sink = RedisEventSink(redis, run_id, ttl_seconds=60)
    await sink.emit("token", text="before")
    await sink.emit("some_future_event", payload={"k": "v"})  # unknown type
    await sink.emit("token", text="after")
    await sink.emit("done", final_text="before after")
    await asyncio.wait_for(task, timeout=2)

    frames = b"".join(collected)
    # The unknown event was forwarded verbatim and did not break the stream…
    assert b"event: some_future_event" in frames
    # …and the known events around it parsed and forwarded fine, terminating on done.
    assert b"before" in frames and b"after" in frames
    assert b"event: done" in frames

    # The parser/deserializer (json.loads of each frame's data) accepts the unknown
    # event: every forwarded frame is valid JSON, including the unrecognized type.
    for frame in collected:
        for line in frame.split(b"\n"):
            if line.startswith(b"data: "):
                parsed = json.loads(line[len(b"data: ") :])
                assert "type" in parsed  # unknown types carry the same envelope


async def test_sse_forwards_live_events_then_closes(redis: Any) -> None:
    import asyncio

    run_id = str(uuid4())
    collected: list[bytes] = []

    async def consume() -> None:
        async for frame in sse_stream(redis, run_id, heartbeat_seconds=5):
            collected.append(frame)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the subscriber attach
    sink = RedisEventSink(redis, run_id, ttl_seconds=60)
    await sink.emit("token", text="Hello ")
    await sink.emit("token", text="world")
    await sink.emit("done", final_text="Hello world")
    await asyncio.wait_for(task, timeout=2)

    text = b"".join(collected)
    assert b"Hello " in text and b"world" in text
    assert b"event: done" in text  # AC3: terminal closes the stream
