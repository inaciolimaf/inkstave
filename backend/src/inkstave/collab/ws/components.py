"""Per-instance collaboration components wired onto ``app.state.collab`` (spec 29)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.collab.awareness import AwarenessRegistry
from inkstave.collab.content_bridge import ContentBridge
from inkstave.collab.manager import CollabSettings, DocumentManager
from inkstave.collab.store import CrdtStore, SessionFactory
from inkstave.collab.ws.redis_bridge import RedisBridge, Subscription
from inkstave.collab.ws.rooms import RoomManager
from inkstave.history.capture import HistoryCaptureService
from inkstave.storage.factory import get_object_store

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.config import Settings


@dataclass(frozen=True, slots=True)
class CollabWsSettings:
    max_frame_bytes: int
    send_queue_max: int
    slow_client_timeout_ms: int
    max_msgs_per_sec: int
    ping_interval_seconds: float
    pong_timeout_seconds: float
    channel_prefix: str
    max_update_bytes: int

    @classmethod
    def from_settings(cls, settings: Settings) -> CollabWsSettings:
        return cls(
            max_frame_bytes=settings.collab_ws_max_frame_bytes,
            send_queue_max=settings.collab_ws_send_queue_max,
            slow_client_timeout_ms=settings.collab_ws_slow_client_timeout_ms,
            max_msgs_per_sec=settings.collab_ws_max_msgs_per_sec,
            ping_interval_seconds=settings.collab_ws_ping_interval_seconds,
            pong_timeout_seconds=settings.collab_ws_pong_timeout_seconds,
            channel_prefix=settings.collab_redis_channel_prefix,
            max_update_bytes=settings.collab_max_update_bytes,
        )


@dataclass
class CollabComponents:
    manager: DocumentManager
    rooms: RoomManager
    awareness: AwarenessRegistry
    redis_bridge: RedisBridge
    session_factory: SessionFactory
    ws_settings: CollabWsSettings
    history: HistoryCaptureService | None = None
    subscriptions: dict[UUID, Subscription] = field(default_factory=dict)


def build_collab_components(
    *,
    redis: Redis,
    session_factory: SessionFactory,
    settings: Settings,
    instance_id: str,
) -> CollabComponents:
    awareness = AwarenessRegistry()
    manager = DocumentManager(
        store=CrdtStore(session_factory),
        content_bridge=ContentBridge(session_factory),
        awareness=awareness,
        settings=CollabSettings.from_settings(settings),
    )
    history: HistoryCaptureService | None = None
    if settings.history_capture_enabled:
        history = HistoryCaptureService(session_factory, get_object_store(settings), settings)
    return CollabComponents(
        manager=manager,
        # Plumb the slow-client grace window so a momentarily-full send queue gets a
        # short timed put before the socket is ejected with 4408 (spec 68 #108).
        rooms=RoomManager(settings.collab_ws_slow_client_timeout_ms),
        awareness=awareness,
        redis_bridge=RedisBridge(redis, instance_id, settings.collab_redis_channel_prefix),
        session_factory=session_factory,
        ws_settings=CollabWsSettings.from_settings(settings),
        history=history,
    )
