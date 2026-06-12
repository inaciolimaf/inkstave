"""Binary file service: streaming upload (hash + size guard + MIME), download,
delete (spec 14). Blob writes are best-effort-cleaned on any DB failure so no
orphan blob or entity is left behind.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from inkstave.config import get_settings
from inkstave.db.models.file import File
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.errors import AppError, ConflictError, NotFoundError
from inkstave.services import tree_service
from inkstave.storage.base import ObjectNotFoundError, ObjectStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Reader for the upload body: returns up to ``size`` bytes, empty when exhausted.
ByteReader = Callable[[int], Awaitable[bytes]]


class NotAFileError(ConflictError):
    error_type = "not_a_file"

    def __init__(self) -> None:
        super().__init__("This entity is not a file.")


class FileTooLargeError(AppError):
    status_code = 413
    error_type = "file_too_large"

    def __init__(self) -> None:
        super().__init__("The uploaded file exceeds the maximum allowed size.")


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    error_type = "unsupported_media_type"

    def __init__(self) -> None:
        super().__init__("This file type is not allowed.")


class BlobMissingError(NotFoundError):
    error_type = "file_blob_missing"

    def __init__(self) -> None:
        super().__init__("The file's stored content is missing.")


_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)


def sniff_content_type(head: bytes, declared: str | None) -> str:
    """Best-effort content-type detection from magic bytes, else the declared type."""
    for signature, content_type in _SIGNATURES:
        if head.startswith(signature):
            return content_type
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return declared or "application/octet-stream"


def _storage_key(project_id: UUID, file_id: UUID) -> str:
    return f"projects/{project_id}/files/{file_id}"


async def _get_file_entity(session: AsyncSession, project_id: UUID, entity_id: UUID) -> TreeEntity:
    entity = (
        await session.execute(
            select(TreeEntity).where(
                TreeEntity.id == entity_id, TreeEntity.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if entity is None:
        raise tree_service.EntityNotFoundError()
    if entity.type is not TreeEntityType.file:
        raise NotAFileError()
    return entity


async def get_file(session: AsyncSession, project_id: UUID, entity_id: UUID) -> File:
    await _get_file_entity(session, project_id, entity_id)
    file_row = (
        await session.execute(select(File).where(File.entity_id == entity_id))
    ).scalar_one_or_none()
    if file_row is None:
        raise tree_service.EntityNotFoundError()
    return file_row


async def upload_file(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    parent_id: UUID | None,
    name: str,
    read: ByteReader,
    declared_content_type: str | None,
    original_filename: str | None,
) -> File:
    settings = get_settings()
    chunk_size = settings.storage_stream_chunk_bytes

    # Create the file tree entity first (validates name, resolves the folder
    # parent, and rejects duplicate sibling names).
    entity = await tree_service.create_entity(
        session, project_id, TreeEntityType.file, name, parent_id
    )
    key = _storage_key(project_id, entity.id)

    head = await read(chunk_size)
    content_type = sniff_content_type(head, declared_content_type)
    if content_type not in settings.allowed_upload_mime:
        raise UnsupportedMediaTypeError()

    hasher = hashlib.sha256()
    total = {"size": 0}

    async def body() -> AsyncIterator[bytes]:
        chunk = head
        while chunk:
            total["size"] += len(chunk)
            if total["size"] > settings.max_upload_bytes:
                raise FileTooLargeError()
            hasher.update(chunk)
            yield chunk
            chunk = await read(chunk_size)

    try:
        await store.put(key, body(), content_type=content_type)
        file_row = File(
            entity_id=entity.id,
            project_id=project_id,
            storage_key=key,
            content_type=content_type,
            size_bytes=total["size"],
            checksum_sha256=hasher.hexdigest(),
            original_filename=original_filename[:255] if original_filename else None,
        )
        session.add(file_row)
        await session.flush()
        await session.refresh(file_row)
    except BaseException:
        # The DB transaction rolls back the entity; clean up any stored blob.
        await store.delete(key)
        raise
    return file_row


async def open_file_content(
    session: AsyncSession, store: ObjectStore, project_id: UUID, entity_id: UUID
) -> tuple[File, AsyncIterator[bytes]]:
    file_row = await get_file(session, project_id, entity_id)
    try:
        _, stream = await store.open(file_row.storage_key)
    except ObjectNotFoundError as exc:
        raise BlobMissingError() from exc
    return file_row, stream


async def delete_file(
    session: AsyncSession, store: ObjectStore, project_id: UUID, entity_id: UUID
) -> None:
    await get_file(session, project_id, entity_id)
    # Removes the tree entity (cascades the files row) and deletes the blob.
    await tree_service.delete_entity(session, project_id, entity_id, store=store)
