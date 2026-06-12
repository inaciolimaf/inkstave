"""Local filesystem object store.

Keys map to paths under a resolved base directory; the final path must stay
inside the base (defence-in-depth against traversal, even though keys are
server-generated). Writes go to a temp file then ``os.replace`` (atomic).
Blocking file I/O runs in a thread so the event loop is not stalled.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore, PutData


async def _as_chunks(data: PutData) -> AsyncIterator[bytes]:
    if isinstance(data, bytes):
        yield data
        return
    async for chunk in data:
        yield chunk


def _safe_unlink(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


class LocalObjectStore(ObjectStore):
    def __init__(self, base_path: Path, chunk_size: int) -> None:
        self._base = base_path.resolve()
        self._chunk = chunk_size

    def _path(self, key: str) -> Path:
        candidate = (self._base / key).resolve()
        if candidate != self._base and not candidate.is_relative_to(self._base):
            raise ValueError("storage key escapes the base directory")
        return candidate

    async def put(self, key: str, data: PutData, *, content_type: str | None = None) -> ObjectStat:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
        size = 0
        try:
            handle: BinaryIO = await asyncio.to_thread(open, tmp, "wb")
            try:
                async for chunk in _as_chunks(data):
                    await asyncio.to_thread(handle.write, chunk)
                    size += len(chunk)
            finally:
                await asyncio.to_thread(handle.close)
            await asyncio.to_thread(os.replace, tmp, path)
        except BaseException:
            await asyncio.to_thread(_safe_unlink, tmp)
            raise
        return ObjectStat(size=size, content_type=content_type)

    async def stat(self, key: str) -> ObjectStat:
        path = self._path(key)
        try:
            result = await asyncio.to_thread(path.stat)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc
        return ObjectStat(size=result.st_size)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(_safe_unlink, self._path(key))

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).exists)

    async def open(self, key: str) -> tuple[ObjectStat, AsyncIterator[bytes]]:
        stat = await self.stat(key)
        return stat, self._read(key)

    async def _read(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        handle: BinaryIO = await asyncio.to_thread(open, path, "rb")
        try:
            while True:
                chunk = await asyncio.to_thread(handle.read, self._chunk)
                if not chunk:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def read_range(self, key: str, start: int, end: int) -> AsyncIterator[bytes]:
        path = self._path(key)
        remaining = end - start + 1
        handle: BinaryIO = await asyncio.to_thread(open, path, "rb")
        try:
            await asyncio.to_thread(handle.seek, start)
            while remaining > 0:
                chunk = await asyncio.to_thread(handle.read, min(self._chunk, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)
