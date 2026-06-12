"""OutputStore: persist compile artifacts into spec-14 storage + range helpers (spec 23)."""

from __future__ import annotations

import asyncio
import enum
import hashlib
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.db.models.compile_output import CompileOutput, OutputKind

if TYPE_CHECKING:
    from inkstave.compile.output_repository import OutputRepository
    from inkstave.compile.result import CompileResult
    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore

_AUX_SUFFIXES = (".aux", ".fls", ".fdb_latexmk", ".out", ".toc", ".bbl", ".blg")


def _sha256_hex(data: bytes) -> str:
    """SHA-256 hex digest, isolated so it can run via ``asyncio.to_thread``."""
    return hashlib.sha256(data).hexdigest()


# Module-level logger (spec 23 §5.2.2 default). A caller may inject its own bound
# logger via ``OutputStore(logger=...)``; existing call sites get this default.
logger = logging.getLogger("inkstave.compile.outputs")


def classify(name: str) -> OutputKind:
    lower = name.lower()
    if lower.endswith(".pdf"):
        return OutputKind.PDF
    if lower.endswith(".log"):
        return OutputKind.LOG
    if lower.endswith(".synctex.gz"):
        return OutputKind.SYNCTEX
    if lower.endswith(_AUX_SUFFIXES):
        return OutputKind.AUX
    return OutputKind.OTHER


class RangeResult(enum.Enum):
    FULL = "full"  # no/blank Range header — serve the whole object (200)
    UNSATISFIABLE = "unsatisfiable"  # 416


@dataclass(slots=True)
class ByteRange:
    start: int
    end: int  # inclusive

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_range(header: str | None, total: int) -> ByteRange | RangeResult:
    """Parse an HTTP ``Range: bytes=…`` header against a known total size."""
    if not header:
        return RangeResult.FULL
    match = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header)
    if not match:
        return RangeResult.FULL  # ignore malformed Range -> full body
    start_s, end_s = match.group(1), match.group(2)
    if start_s == "" and end_s == "":
        return RangeResult.FULL
    if start_s == "":  # suffix range: last N bytes
        suffix = int(end_s)
        if suffix == 0:
            return RangeResult.UNSATISFIABLE
        start = max(0, total - suffix)
        end = total - 1
    else:
        start = int(start_s)
        end = min(int(end_s), total - 1) if end_s else total - 1
    if start >= total or start > end:
        return RangeResult.UNSATISFIABLE
    return ByteRange(start, end)


@dataclass(slots=True)
class StoredObject:
    size: int
    content_type: str
    etag: str
    store: ObjectStore
    key: str

    async def stream(self) -> AsyncIterator[bytes]:
        iterator = await self.store.get(self.key)
        async for chunk in iterator:
            yield chunk

    def read_range(self, start: int, end: int) -> AsyncIterator[bytes]:
        return self.store.read_range(self.key, start, end)


class OutputStore:
    def __init__(
        self,
        *,
        storage: ObjectStore,
        repo: OutputRepository,
        settings: Settings,
        logger: logging.Logger = logger,
    ) -> None:
        self._storage = storage
        self._repo = repo
        self._settings = settings
        self._logger = logger

    def _key(self, project_id: UUID, compile_id: UUID, name: str) -> str:
        return f"{self._settings.compile_output_prefix}/{project_id}/{compile_id}/{name}"

    async def persist(
        self, compile_id: UUID, project_id: UUID, result: CompileResult
    ) -> list[CompileOutput]:
        """Copy every artifact into storage and upsert its metadata row. Idempotent."""
        rows: list[CompileOutput] = []
        for artifact in result.artifacts:
            data = await asyncio.to_thread(artifact.abs_path.read_bytes)
            etag = await asyncio.to_thread(_sha256_hex, data)
            key = self._key(project_id, compile_id, artifact.name)
            await self._storage.put(key, data, content_type=artifact.content_type)
            row = await self._repo.upsert(
                compile_id=compile_id,
                project_id=project_id,
                name=artifact.name,
                rel_path=artifact.rel_path,
                kind=classify(artifact.name).value,
                content_type=artifact.content_type,
                size_bytes=len(data),
                storage_key=key,
                etag=etag,
            )
            rows.append(row)
        self._logger.debug(
            "persisted compile outputs",
            extra={"compile_id": str(compile_id), "count": len(rows)},
        )
        return rows

    def _stored(self, row: CompileOutput) -> StoredObject:
        return StoredObject(
            size=row.size_bytes,
            content_type=row.content_type,
            etag=row.etag,
            store=self._storage,
            key=row.storage_key,
        )

    async def open_pdf(self, compile_id: UUID) -> StoredObject | None:
        row = await self._repo.get_by_kind(compile_id, OutputKind.PDF.value)
        return self._stored(row) if row is not None else None

    async def open_log(self, compile_id: UUID) -> StoredObject | None:
        row = await self._repo.get_by_kind(compile_id, OutputKind.LOG.value)
        return self._stored(row) if row is not None else None

    async def open_synctex(self, compile_id: UUID) -> StoredObject | None:
        row = await self._repo.get_by_kind(compile_id, OutputKind.SYNCTEX.value)
        return self._stored(row) if row is not None else None

    async def list_outputs(self, compile_id: UUID) -> list[CompileOutput]:
        return await self._repo.list_for_compile(compile_id)

    async def delete_for_compile(self, compile_id: UUID) -> None:
        # Delete storage objects BEFORE the rows. Storage delete is idempotent
        # (missing keys are a no-op), so a failure mid-sweep leaves the rows in
        # place and the next retention pass retries cleanly — no orphaned bytes.
        keys = await self._repo.storage_keys_for_compile(compile_id)
        for key in keys:
            await self._storage.delete(key)
        await self._repo.delete_for_compile(compile_id)

    async def delete_for_project(self, project_id: UUID) -> None:
        keys = await self._repo.storage_keys_for_project(project_id)
        for key in keys:
            await self._storage.delete(key)
        await self._repo.delete_for_project(project_id)
