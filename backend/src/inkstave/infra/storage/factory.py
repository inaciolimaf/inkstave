"""Object-store factory: pick a backend from settings."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from inkstave.infra.storage.base import ObjectStore
from inkstave.infra.storage.local import LocalObjectStore

if TYPE_CHECKING:
    from inkstave.core.config.settings import Settings


def get_object_store(settings: Settings) -> ObjectStore:
    """Construct the configured object store (``local`` or ``s3``)."""
    if settings.file_storage_backend == "s3":
        from inkstave.infra.storage.s3 import S3ObjectStore, client_config

        return S3ObjectStore(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            chunk_size=settings.storage_stream_chunk_bytes,
            endpoint_url=settings.s3_endpoint_url or None,
            access_key=settings.s3_access_key_id or None,
            secret_key=settings.s3_secret_access_key or None,
            config=client_config(
                connect_timeout_s=settings.s3_connect_timeout_s,
                read_timeout_s=settings.s3_read_timeout_s,
            ),
        )
    return LocalObjectStore(
        Path(settings.file_storage_local_path),
        settings.storage_stream_chunk_bytes,
    )
