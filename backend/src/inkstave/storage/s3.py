"""S3-compatible object store (AWS S3 / MinIO) via aioboto3.

GET buffers the object in memory within the client context for simplicity
(documented in the ADR); the default ``local`` backend streams. ``NoSuchKey`` /
404 responses are translated to :class:`ObjectNotFoundError`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import aioboto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from inkstave.storage.base import ObjectNotFoundError, ObjectStat, ObjectStore, PutData


def _is_not_found(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code", "")
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in ("NoSuchKey", "NotFound", "404") or status == 404


async def _chunked(data: bytes, size: int) -> AsyncIterator[bytes]:
    for offset in range(0, len(data), size):
        yield data[offset : offset + size]


class S3ObjectStore(ObjectStore):
    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        chunk_size: int,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._chunk = chunk_size
        self._client_kwargs: dict[str, Any] = {"service_name": "s3", "region_name": region}
        if endpoint_url:
            self._client_kwargs["endpoint_url"] = endpoint_url
        if access_key:
            self._client_kwargs["aws_access_key_id"] = access_key
        if secret_key:
            self._client_kwargs["aws_secret_access_key"] = secret_key
        self._session = aioboto3.Session()

    def _client(self) -> Any:
        return self._session.client(**self._client_kwargs)

    async def put(self, key: str, data: PutData, *, content_type: str | None = None) -> ObjectStat:
        body = data if isinstance(data, bytes) else b"".join([chunk async for chunk in data])
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key, "Body": body}
        if content_type:
            kwargs["ContentType"] = content_type
        async with self._client() as s3:
            await s3.put_object(**kwargs)
        return ObjectStat(size=len(body), content_type=content_type)

    async def stat(self, key: str) -> ObjectStat:
        async with self._client() as s3:
            try:
                resp = await s3.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if _is_not_found(exc):
                    raise ObjectNotFoundError(key) from exc
                raise
        return ObjectStat(size=resp["ContentLength"], content_type=resp.get("ContentType"))

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)  # idempotent in S3

    async def exists(self, key: str) -> bool:
        try:
            await self.stat(key)
        except ObjectNotFoundError:
            return False
        return True

    async def open(self, key: str) -> tuple[ObjectStat, AsyncIterator[bytes]]:
        async with self._client() as s3:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if _is_not_found(exc):
                    raise ObjectNotFoundError(key) from exc
                raise
            data: bytes = await resp["Body"].read()
            content_type = resp.get("ContentType")
        return ObjectStat(size=len(data), content_type=content_type), _chunked(data, self._chunk)
