"""Unit tests for SyncTexService: resolution, size guard, and the parse cache (spec 26)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from inkstave.config import Settings
from inkstave.synctex.service import SyncTexNotAvailable, SyncTexService
from tests.synctex_fixtures import SINGLE_FILE, gz


class _Row:
    def __init__(self) -> None:
        self.id = uuid4()


class _FakeRepo:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    async def get(self, project_id: object, compile_id: object) -> _Row | None:
        return self._row

    async def get_latest_successful(self, project_id: object) -> _Row | None:
        return self._row


class _FakeStored:
    def __init__(self, data: bytes, *, size: int | None = None, etag: str = "etag-1") -> None:
        self._data = data
        self.size = size if size is not None else len(data)
        self.etag = etag
        self.reads = 0

    async def stream(self) -> AsyncIterator[bytes]:
        self.reads += 1
        yield self._data


class _FakeStore:
    def __init__(self, obj: _FakeStored | None) -> None:
        self._obj = obj

    async def open_synctex(self, compile_id: object) -> _FakeStored | None:
        return self._obj


def _settings(**over: object) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def _service(store: _FakeStore, row: _Row | None = None, **over: object) -> SyncTexService:
    return SyncTexService(
        repo=_FakeRepo(row if row is not None else _Row()),  # type: ignore[arg-type]
        output_store=store,  # type: ignore[arg-type]
        settings=_settings(**over),
    )


async def test_missing_compile_is_unavailable() -> None:
    service = SyncTexService(
        repo=_FakeRepo(None),  # type: ignore[arg-type]
        output_store=_FakeStore(_FakeStored(gz(SINGLE_FILE))),  # type: ignore[arg-type]
        settings=_settings(),
    )
    with pytest.raises(SyncTexNotAvailable):
        await service.load_index(uuid4(), None)


async def test_no_synctex_artifact_is_unavailable() -> None:
    service = _service(_FakeStore(None))
    with pytest.raises(SyncTexNotAvailable):
        await service.load_index(uuid4(), None)


async def test_oversize_synctex_is_refused() -> None:
    big = _FakeStored(gz(SINGLE_FILE), size=10_000_000)
    service = _service(_FakeStore(big), synctex_max_gz_bytes=1)
    with pytest.raises(SyncTexNotAvailable):
        await service.load_index(uuid4(), None)


async def test_index_is_cached_by_etag() -> None:
    row = _Row()
    obj = _FakeStored(gz(SINGLE_FILE), etag="stable")
    service = _service(_FakeStore(obj), row=row, synctex_index_cache_size=16)
    first = await service.load_index(uuid4(), str(row.id))
    second = await service.load_index(uuid4(), str(row.id))
    assert first is second  # same parsed object, served from cache
    assert obj.reads == 1  # bytes streamed only once


async def test_cache_disabled_reparses() -> None:
    row = _Row()
    obj = _FakeStored(gz(SINGLE_FILE), etag="stable-2")
    service = _service(_FakeStore(obj), row=row, synctex_index_cache_size=0)
    first = await service.load_index(uuid4(), str(row.id))
    second = await service.load_index(uuid4(), str(row.id))
    assert first is not second
    assert obj.reads == 2
