"""Project → streaming ``.zip`` export (spec 102).

Pure read over ``tree_entities`` / ``documents`` / ``files`` + blob storage. The
archive is produced as a true stream (stdlib ``zipfile`` writing into a small
drain-as-you-go buffer) so a large project never materialises the whole archive
in memory. Entry order is deterministic (folders before their children) so tests
can assert exact contents.

Independent implementation; shares no code with Overleaf's archiver-based
``ProjectZipStreamManager`` (read for understanding only — AGPLv3 vs MIT).
"""

from __future__ import annotations

import io
import logging
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select

from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.errors import AppError
from inkstave.services import tree_service
from inkstave.services.tree_builder import compute_path
from inkstave.storage.base import ObjectNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore

logger = logging.getLogger(__name__)

# The zip epoch — a fixed timestamp on every entry makes the archive reproducible.
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_DIR_EXTERNAL_ATTR = (0o040755 << 16) | 0x10  # drwxr-xr-x + MS-DOS directory bit
_FILE_EXTERNAL_ATTR = 0o100644 << 16  # -rw-r--r--


class ExportTooLargeError(AppError):
    status_code = 413
    error_type = "export_too_large"

    def __init__(self) -> None:
        super().__init__("The project is too large to export.")


@dataclass(frozen=True)
class ExportEntry:
    path: str  # POSIX relative path inside the zip, e.g. "chapters/intro.tex"
    type: TreeEntityType
    entity_id: UUID
    storage_key: str | None  # set for file entities
    size_bytes: int  # doc UTF-8 size or file size; 0 for folders


def _assert_safe_path(path: str) -> None:
    """Defensive zip-slip guard: every segment is a safe, non-traversal name."""
    for segment in path.split("/"):
        if not segment or segment in (".", "..") or "\\" in segment:
            raise ValueError(f"unsafe archive path segment in {path!r}")


async def _doc_sizes(session: AsyncSession, project_id: UUID) -> dict[UUID, int]:
    rows = (
        await session.execute(
            select(Document.entity_id, Document.size_bytes).where(Document.project_id == project_id)
        )
    ).all()
    return {eid: int(size) for eid, size in rows}


async def _file_rows(session: AsyncSession, project_id: UUID) -> dict[UUID, tuple[str | None, int]]:
    rows = (
        await session.execute(
            select(File.entity_id, File.storage_key, File.size_bytes).where(
                File.project_id == project_id
            )
        )
    ).all()
    return {eid: (key, int(size)) for eid, key, size in rows}


def _plan_entry(
    entity: TreeEntity,
    path: str,
    doc_sizes: dict[UUID, int],
    file_rows: dict[UUID, tuple[str | None, int]],
) -> ExportEntry:
    """One plan row; folders carry no bytes, docs and files carry their size."""
    if entity.type is TreeEntityType.folder:
        return ExportEntry(path, entity.type, entity.id, None, 0)
    if entity.type is TreeEntityType.doc:
        return ExportEntry(path, entity.type, entity.id, None, doc_sizes.get(entity.id, 0))
    key, size = file_rows.get(entity.id, (None, 0))
    return ExportEntry(path, entity.type, entity.id, key, size)


async def build_export_plan(
    session: AsyncSession, project_id: UUID, settings: Settings
) -> list[ExportEntry]:
    """Build the deterministic, root-relative export plan and enforce the size cap."""
    entities = await tree_service.get_tree(session, project_id)
    by_id = {e.id: e for e in entities}
    # Bulk metadata reads (one SELECT each) so the plan never issues N queries.
    doc_sizes = await _doc_sizes(session, project_id)
    file_rows = await _file_rows(session, project_id)

    entries: list[ExportEntry] = []
    for entity in entities:
        if entity.is_root:
            continue
        path = compute_path(entity, by_id)
        _assert_safe_path(path)
        entries.append(_plan_entry(entity, path, doc_sizes, file_rows))

    total = sum(e.size_bytes for e in entries)
    if total > settings.export_max_total_bytes and not settings.export_async_enabled:
        raise ExportTooLargeError()

    # Deterministic order: sort by the *segment list* so a folder ("a") always
    # precedes its contents ("a/b.tex") — plain string ordering would not
    # guarantee that ('/' is not below all name characters).
    entries.sort(key=lambda e: e.path.split("/"))
    return entries


class _StreamBuffer(io.RawIOBase):
    """A write-only sink that accumulates bytes for the generator to drain."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, b: bytes) -> int:  # type: ignore[override]
        self._buf += b
        return len(b)

    def drain(self) -> bytes:
        data = bytes(self._buf)
        self._buf.clear()
        return data

    def pending(self) -> int:
        return len(self._buf)


async def _doc_contents(session: AsyncSession, plan: list[ExportEntry]) -> dict[UUID, str]:
    """One bulk read of doc text (post-flush) keyed by entity id — no N queries."""
    doc_ids = [e.entity_id for e in plan if e.type is TreeEntityType.doc]
    if not doc_ids:
        return {}
    rows = (
        await session.execute(
            select(Document.entity_id, Document.content).where(Document.entity_id.in_(doc_ids))
        )
    ).all()
    return {eid: content for eid, content in rows}


def _zip_info(path: str, *, is_dir: bool = False) -> zipfile.ZipInfo:
    """A deterministic entry header (fixed timestamp + fixed permissions)."""
    info = zipfile.ZipInfo(path + "/" if is_dir else path, date_time=_FIXED_DATE_TIME)
    if is_dir:
        info.external_attr = _DIR_EXTERNAL_ATTR
        return info
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = _FILE_EXTERNAL_ATTR
    return info


async def _write_blob(
    zf: zipfile.ZipFile,
    buffer: _StreamBuffer,
    entry: ExportEntry,
    store: ObjectStore,
    chunk_size: int,
) -> AsyncIterator[bytes]:
    """Stream one stored file into the archive, flushing the buffer as it fills."""
    if entry.storage_key is None:
        return
    try:
        _, stream = await store.open(entry.storage_key)
    except ObjectNotFoundError:
        # Storage desync: skip the orphaned entry, never abort the export.
        logger.warning("export: blob missing for entity %s; skipping", entry.entity_id)
        return
    with zf.open(_zip_info(entry.path), mode="w") as dest:
        async for chunk in stream:
            dest.write(chunk)
            if buffer.pending() >= chunk_size:
                yield buffer.drain()
    yield buffer.drain()


async def stream_project_zip(
    plan: list[ExportEntry],
    store: ObjectStore,
    session: AsyncSession,
    settings: Settings,
) -> AsyncIterator[bytes]:
    """Yield the project archive as a stream — never the whole zip at once."""
    contents = await _doc_contents(session, plan)
    chunk_size = settings.storage_stream_chunk_bytes
    buffer = _StreamBuffer()
    zf = zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED)
    try:
        for entry in plan:
            if entry.type is TreeEntityType.folder:
                zf.writestr(_zip_info(entry.path, is_dir=True), b"")
                yield buffer.drain()
            elif entry.type is TreeEntityType.doc:
                with zf.open(_zip_info(entry.path), mode="w") as dest:
                    dest.write(contents.get(entry.entity_id, "").encode("utf-8"))
                yield buffer.drain()
            else:  # file
                async for chunk in _write_blob(zf, buffer, entry, store, chunk_size):
                    yield chunk
    finally:
        zf.close()
    yield buffer.drain()  # the central directory written by close()


# --------------------------------------------------------------------------- #
# Filename / Content-Disposition helpers
# --------------------------------------------------------------------------- #


def zip_filename_for(project_name: str) -> str:
    """Derive a safe ``<name>.zip`` from a project name (fallback ``project.zip``)."""
    cleaned = "".join(" " if ord(ch) < 0x20 else ch for ch in project_name)
    cleaned = cleaned.replace("/", " ").replace("\\", " ").replace('"', "")
    cleaned = " ".join(cleaned.split()).strip()
    return f"{cleaned or 'project'}.zip"


def content_disposition(filename: str) -> str:
    """An ``attachment`` Content-Disposition with ASCII + RFC 5987 UTF-8 forms."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    ascii_name = ascii_name.replace('"', "").replace("\r", "").replace("\n", "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
