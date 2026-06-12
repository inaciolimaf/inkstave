"""Unit tests for the object-storage backends and factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from inkstave.config import Settings
from inkstave.storage.base import ObjectNotFoundError
from inkstave.storage.factory import get_object_store
from inkstave.storage.local import LocalObjectStore
from inkstave.storage.s3 import S3ObjectStore


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in stream])


# --- LocalObjectStore -------------------------------------------------------- #


@pytest.fixture
def local_store(tmp_path: Any) -> LocalObjectStore:
    return LocalObjectStore(tmp_path, 8)  # tiny chunk to exercise streaming


async def test_local_put_get_stat_exists(local_store: LocalObjectStore) -> None:
    stat = await local_store.put("projects/p/files/f", b"hello world", content_type="text/plain")
    assert stat.size == 11
    assert await local_store.exists("projects/p/files/f")
    assert (await local_store.stat("projects/p/files/f")).size == 11
    _, stream = await local_store.open("projects/p/files/f")
    assert await _collect(stream) == b"hello world"


async def test_local_streams_in_chunks(local_store: LocalObjectStore) -> None:
    await local_store.put("k", b"0123456789")
    _, stream = await local_store.open("k")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 2  # 8 + 2 with chunk size 8
    assert b"".join(chunks) == b"0123456789"


async def test_local_put_from_stream(local_store: LocalObjectStore) -> None:
    async def gen() -> AsyncIterator[bytes]:
        yield b"ab"
        yield b"cd"

    await local_store.put("k", gen())
    _, stream = await local_store.open("k")
    assert await _collect(stream) == b"abcd"


async def test_local_missing_and_delete(local_store: LocalObjectStore) -> None:
    with pytest.raises(ObjectNotFoundError):
        await local_store.stat("nope")
    assert await local_store.exists("nope") is False
    await local_store.delete("nope")  # idempotent: no error


def test_local_rejects_traversal_key(local_store: LocalObjectStore) -> None:
    with pytest.raises(ValueError, match="escapes"):
        local_store._path("../../etc/passwd")


async def test_objectstore_get_streams(local_store: LocalObjectStore) -> None:
    # Exercises the base-class ``get`` convenience (open + return stream).
    await local_store.put("k", b"streamed")
    stream = await local_store.get("k")
    assert await _collect(stream) == b"streamed"


# --- factory + settings validation ------------------------------------------ #


def test_factory_selects_local() -> None:
    settings = Settings(_env_file=None, file_storage_backend="local")  # type: ignore[call-arg]
    assert isinstance(get_object_store(settings), LocalObjectStore)


def test_factory_selects_s3() -> None:
    settings = Settings(_env_file=None, file_storage_backend="s3", s3_bucket="b")  # type: ignore[call-arg]
    assert isinstance(get_object_store(settings), S3ObjectStore)


def test_s3_requires_bucket() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, file_storage_backend="s3", s3_bucket="")  # type: ignore[call-arg]


# --- S3ObjectStore against a faked client (no network) ---------------------- #


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self, backing: dict[str, tuple[bytes, str | None]]) -> None:
        self._d = backing

    async def put_object(
        self, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None
    ) -> None:
        self._d[Key] = (Body, ContentType)

    async def head_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._d:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )
        body, content_type = self._d[Key]
        return {"ContentLength": len(body), "ContentType": content_type}

    async def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self._d:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body, content_type = self._d[Key]
        return {"ContentLength": len(body), "ContentType": content_type, "Body": _FakeBody(body)}

    async def delete_object(self, Bucket: str, Key: str) -> None:
        self._d.pop(Key, None)


class _FakeClientCM:
    def __init__(self, client: _FakeS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> _FakeS3Client:
        return self._client

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_s3_roundtrip_and_notfound(monkeypatch: pytest.MonkeyPatch) -> None:
    store = S3ObjectStore(bucket="b", region="us-east-1", chunk_size=4)
    backing: dict[str, tuple[bytes, str | None]] = {}
    monkeypatch.setattr(store, "_client", lambda: _FakeClientCM(_FakeS3Client(backing)))

    await store.put("k", b"hi there", content_type="text/plain")
    assert backing["k"][0] == b"hi there"
    assert (await store.stat("k")).size == 8
    _, stream = await store.open("k")
    assert await _collect(stream) == b"hi there"
    assert await store.exists("k") is True

    with pytest.raises(ObjectNotFoundError):
        await store.stat("missing")
    await store.delete("missing")  # idempotent
    await store.delete("k")
    assert await store.exists("k") is False


async def test_s3_with_endpoint_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    store = S3ObjectStore(
        bucket="b",
        region="us-east-1",
        chunk_size=4,
        endpoint_url="http://minio:9000",
        access_key="ak",
        secret_key="sk",
    )
    assert store._client_kwargs["endpoint_url"] == "http://minio:9000"
    assert store._client_kwargs["aws_access_key_id"] == "ak"
    assert store._client_kwargs["aws_secret_access_key"] == "sk"

    backing: dict[str, tuple[bytes, str | None]] = {}
    monkeypatch.setattr(store, "_client", lambda: _FakeClientCM(_FakeS3Client(backing)))
    await store.put("k", b"data")
    assert await _collect(await store.get("k")) == b"data"
