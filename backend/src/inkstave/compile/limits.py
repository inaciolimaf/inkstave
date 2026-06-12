"""Resource limits and cooperative cancellation (spec 21)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ResourceLimits:
    max_input_files: int
    max_input_bytes: int
    max_output_bytes: int
    max_log_bytes: int
    max_stdout_bytes: int
    cpu_seconds: int | None
    address_space_bytes: int | None


class CancelToken:
    """A lightweight cooperative cancellation flag (wraps ``asyncio.Event``)."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()
