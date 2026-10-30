"""Fire-and-forget tasks that are neither garbage-collected nor silently lost.

The event loop only keeps a weak reference to a task, so a task nobody holds can vanish
mid-flight; and an exception in one is only reported when it is collected, if ever.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)

_running: set[asyncio.Task[None]] = set()


def _finished(task: asyncio.Task[None]) -> None:
    _running.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error("background task %s failed", task.get_name(), exc_info=error)


def spawn(coroutine: Coroutine[Any, Any, None], *, name: str) -> asyncio.Task[None]:
    """Run ``coroutine`` in the background, holding it until done and logging its failure."""
    task = asyncio.create_task(coroutine, name=name)
    _running.add(task)
    task.add_done_callback(_finished)
    return task
