"""S3-compatible object store (AWS S3 / MinIO) via aioboto3.

GET streams the object body in ``chunk_size`` chunks straight off the aiobotocore
``StreamingBody`` — the whole object is never buffered in memory (spec 14 §5.1),
matching the ``local`` backend. The returned async iterator keeps the S3 client
context open until it is exhausted/closed. ``NoSuchKey`` / 404 responses are
translated to :class:`ObjectNotFoundError`.
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
        # We must learn the object's size/content-type *before* returning the body
        # iterator, so issue the GET here (translating not-found) and hand the open
        # streaming body to ``_stream_body``. The client context stays open inside
        # that generator until the body is fully consumed — the whole object is
        # never buffered into memory (spec 14 §5.1).
        cm = self._client()
        s3 = await cm.__aenter__()
        try:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if _is_not_found(exc):
                    raise ObjectNotFoundError(key) from exc
                raise
        except BaseException:
            await cm.__aexit__(None, None, None)
            raise
        size = resp.get("ContentLength")
        content_type = resp.get("ContentType")
        stat = ObjectStat(size=int(size) if size is not None else 0, content_type=content_type)
        return stat, self._stream_body(cm, resp["Body"])

    async def _stream_body(self, cm: Any, body: Any) -> AsyncIterator[bytes]:
        """Yield the object body in ``chunk_size`` chunks, never buffering it whole.

        Prefers the aiobotocore ``StreamingBody.iter_chunks`` async iterator; falls
        back to repeated sized ``read(amt)`` calls. The S3 client context (``cm``) is
        closed when the generator is exhausted or closed, releasing the connection.
        """
        try:
            iter_chunks = getattr(body, "iter_chunks", None)
            if iter_chunks is not None:
                async for chunk in iter_chunks(self._chunk):
                    if chunk:
                        yield chunk
            else:
                # Minimal stub bodies expose only no-arg ``read()``; chunk its result
                # so the iterator contract (and chunk size) still hold.
                data = await body.read()
                for offset in range(0, len(data), self._chunk):
                    yield data[offset : offset + self._chunk]
        finally:
            await cm.__aexit__(None, None, None)
