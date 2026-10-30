"""Object-storage abstraction.

A small async ``ObjectStore`` interface (``put``/``get``/``open``/``delete``/
``exists``/``stat``) with streaming reads, independent of any concrete backend.
``ObjectNotFoundError`` is raised by ``get``/``open``/``stat`` for a missing key
and is mapped to ``404`` at the API.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass


class ObjectNotFoundError(Exception):
    """Raised when a key does not exist in the store."""


@dataclass(frozen=True)
class ObjectStat:
    size: int
    content_type: str | None = None
    checksum: str | None = None


# A byte source for ``put``: either an in-memory bytes object or a stream.
PutData = bytes | AsyncIterator[bytes]


class ObjectStore(abc.ABC):
    """Async object store. Reads stream; writes accept bytes or a stream."""

    @abc.abstractmethod
    async def put(self, key: str, data: PutData, *, content_type: str | None = None) -> ObjectStat:
        """Store bytes under ``key``; returns the resulting stat."""

    @abc.abstractmethod
    async def stat(self, key: str) -> ObjectStat:
        """Return size/metadata for ``key`` or raise :class:`ObjectNotFoundError`."""

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Delete ``key``; a missing key is **not** an error (idempotent)."""

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        """Return whether ``key`` exists."""

    @abc.abstractmethod
    async def open(self, key: str) -> tuple[ObjectStat, AsyncIterator[bytes]]:
        """Return ``(stat, byte-stream)``; raises :class:`ObjectNotFoundError`."""

    async def get(self, key: str) -> AsyncIterator[bytes]:
        """Stream the object's bytes; raises :class:`ObjectNotFoundError`."""
        _, stream = await self.open(key)
        return stream

    async def read_range(self, key: str, start: int, end: int) -> AsyncIterator[bytes]:
        """Stream bytes ``[start, end]`` (inclusive). Default: stream + slice.

        Backends that can seek (e.g. local disk) override this to avoid reading
        the whole object. Raises :class:`ObjectNotFoundError`.
        """
        _, stream = await self.open(key)
        pos = 0
        async for chunk in stream:
            chunk_end = pos + len(chunk)
            if chunk_end <= start:
                pos = chunk_end
                continue
            if pos > end:
                break
            lo = max(0, start - pos)
            hi = min(len(chunk), end - pos + 1)
            yield chunk[lo:hi]
            pos = chunk_end
