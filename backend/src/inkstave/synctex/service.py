"""SyncTeX service: resolve a compile's synctex.gz and answer sync queries (spec 26)."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.synctex.models import ForwardResult, InverseResult
from inkstave.synctex.parser import SyncTexIndex

if TYPE_CHECKING:
    from inkstave.compile.outputs import OutputStore
    from inkstave.compile.repository import CompileRepository
    from inkstave.config import Settings

logger = logging.getLogger(__name__)


class SyncTexNotAvailable(Exception):
    """No usable ``output.synctex.gz`` for the requested compile."""


class _IndexCache:
    """A tiny process-wide LRU of parsed indices keyed by ``(compile_id, etag)``.

    Parsing is pure given the bytes, and a compile's synctex etag is stable, so
    repeated clicks on the same compile reuse the parse. Size 0 disables it.
    """

    def __init__(self) -> None:
        self._store: OrderedDict[tuple[UUID, str], SyncTexIndex] = OrderedDict()
        self._lock = Lock()

    def get(self, key: tuple[UUID, str]) -> SyncTexIndex | None:
        with self._lock:
            index = self._store.get(key)
            if index is not None:
                self._store.move_to_end(key)
            return index

    def put(self, key: tuple[UUID, str], index: SyncTexIndex, capacity: int) -> None:
        if capacity <= 0:
            return
        with self._lock:
            self._store[key] = index
            self._store.move_to_end(key)
            while len(self._store) > capacity:
                self._store.popitem(last=False)


_CACHE = _IndexCache()


class SyncTexService:
    def __init__(
        self, *, repo: CompileRepository, output_store: OutputStore, settings: Settings
    ) -> None:
        self._repo = repo
        self._store = output_store
        self._settings = settings

    async def _resolve_compile_id(self, project_id: UUID, compile_id: str | None) -> UUID:
        if compile_id is not None:
            try:
                cid = UUID(compile_id)
            except ValueError as exc:
                raise SyncTexNotAvailable() from exc
            row = await self._repo.get(project_id, cid)
        else:
            row = await self._repo.get_latest_successful(project_id)
        if row is None:
            raise SyncTexNotAvailable()
        return row.id

    async def load_index(self, project_id: UUID, compile_id: str | None) -> SyncTexIndex:
        cid = await self._resolve_compile_id(project_id, compile_id)
        obj = await self._store.open_synctex(cid)
        if obj is None:
            raise SyncTexNotAvailable()
        if obj.size > self._settings.synctex_max_gz_bytes:
            logger.warning(
                "synctex file for compile %s is %d bytes (> limit %d); refusing to parse",
                cid,
                obj.size,
                self._settings.synctex_max_gz_bytes,
            )
            raise SyncTexNotAvailable()

        key = (cid, obj.etag)
        cached = _CACHE.get(key)
        if cached is not None:
            return cached

        data = b"".join([chunk async for chunk in obj.stream()])
        index = await asyncio.to_thread(SyncTexIndex.from_gz_bytes, data)
        _CACHE.put(key, index, self._settings.synctex_index_cache_size)
        return index

    async def code_to_pdf(
        self, project_id: UUID, compile_id: str | None, file: str, line: int, column: int | None
    ) -> ForwardResult:
        index = await self.load_index(project_id, compile_id)
        return index.forward(file, line, column)

    async def pdf_to_code(
        self, project_id: UUID, compile_id: str | None, page: int, h: float, v: float
    ) -> InverseResult | None:
        index = await self.load_index(project_id, compile_id)
        return index.inverse(page, h, v)
