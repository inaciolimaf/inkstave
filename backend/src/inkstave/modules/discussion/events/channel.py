"""Publishing project events: the one writer of ``project:events:{project_id}`` (spec 117).

Call sites publish only after their transaction has committed. :func:`schedule_project_event`
does that for a route: it queues the publish as a background task, which the framework runs
after the unit of work has committed and the response is out. A failed commit therefore
publishes nothing, and a failed publish is logged, not raised, because the write is already saved.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from redis.asyncio import Redis

logger = logging.getLogger("inkstave.discussion.events")


def project_channel(project_id: UUID) -> str:
    """The Redis pub/sub channel that carries one project's events."""
    return f"project:events:{project_id}"


def _sequence_key(project_id: UUID) -> str:
    return f"project:events:seq:{project_id}"


async def publish_project_event(
    redis: Redis, project_id: UUID, event_type: str, payload: dict[str, Any]
) -> int:
    """Publish one event to the project's stream and return its id.

    The id is a per-project counter, so a client can tell the order of what it saw. Call this
    only after the commit that makes the event true.
    """
    event_id = int(await redis.incr(_sequence_key(project_id)))
    message = {"type": event_type, "payload": payload, "id": event_id}
    await redis.publish(project_channel(project_id), json.dumps(message, default=str))
    return event_id


async def _publish_quietly(redis: Redis, project_id: UUID, event_type: str, payload: dict[str, Any]) -> None:
    try:
        await publish_project_event(redis, project_id, event_type, payload)
    except Exception:
        logger.warning("project event publish failed (type=%s)", event_type, exc_info=True)


def schedule_project_event(
    background: BackgroundTasks,
    redis: Redis,
    project_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Publish an event after the current request's commit, as a background task."""
    background.add_task(_publish_quietly, redis, project_id, event_type, payload)
