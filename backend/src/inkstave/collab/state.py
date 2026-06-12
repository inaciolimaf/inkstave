"""Value types backing :class:`~inkstave.collab.manager.DocumentManager` (spec 28).

The settings record, the oversized-update error, the per-document in-memory entry,
and the acquire handle live here so ``manager.py`` stays focused on lifecycle and
protocol logic. ``manager`` re-exports every public name so importers are unchanged.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from inkstave.collab.manager import DocumentManager
    from inkstave.collab.ydocument import YDocument
    from inkstave.config import Settings


@dataclass(frozen=True, slots=True)
class CollabSettings:
    snapshot_every_updates: int = 200
    snapshot_interval_seconds: float = 30.0
    text_flush_debounce_ms: int = 1000
    idle_evict_seconds: float = 300.0
    max_update_bytes: int = 1_048_576

    @classmethod
    def from_settings(cls, settings: Settings) -> CollabSettings:
        return cls(
            snapshot_every_updates=settings.collab_snapshot_every_updates,
            snapshot_interval_seconds=settings.collab_snapshot_interval_seconds,
            text_flush_debounce_ms=settings.collab_text_flush_debounce_ms,
            idle_evict_seconds=settings.collab_idle_evict_seconds,
            max_update_bytes=settings.collab_max_update_bytes,
        )


class UpdateTooLarge(Exception):
    """A single update exceeded ``COLLAB_MAX_UPDATE_BYTES``."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"update is {size} bytes (limit {limit})")
        self.size = size
        self.limit = limit


@dataclass
class _Entry:
    ydoc: YDocument
    refcount: int = 0
    seq: int = 0
    updates_since_snapshot: int = 0
    last_update_id: int = 0
    last_snapshot_at: float = field(default_factory=monotonic)
    dirty_text: bool = False
    flush_task: asyncio.Task[None] | None = None
    evict_task: asyncio.Task[None] | None = None


class OpenDocument:
    """A handle returned by :meth:`DocumentManager.acquire`."""

    def __init__(self, manager: DocumentManager, document_id: UUID, ydoc: YDocument) -> None:
        self._manager = manager
        self.document_id = document_id
        self.ydoc = ydoc

    @property
    def text(self) -> str:
        return self.ydoc.text

    async def release(self) -> None:
        await self._manager.release(self.document_id)
