"""Rebuild the project tree from a planned archive, reusing the services (spec 101)."""

from __future__ import annotations

import asyncio
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.security.uploads import content_matches_extension
from inkstave.services import document_service, file_service, tree_service
from inkstave.services.file_service import sniff_content_type

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore

from inkstave.services.zip_import.content import decode_text, detect_root_doc
from inkstave.services.zip_import.plan import (
    ImportOutcome,
    ImportPlan,
    PlannedEntry,
    ZipBombError,
)


def _read_member_bounded(zf: zipfile.ZipFile, name: str, max_bytes: int) -> bytes:
    """Read one entry's decompressed bytes, capped so a lying header can't bomb us."""
    with zf.open(name) as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ZipBombError("An archive entry decompressed beyond its declared size.")
    return data


@dataclass
class _FolderCache:
    """Maps a lower-cased path tuple → folder entity id (None == project root)."""

    ids: dict[tuple[str, ...], UUID | None] = field(default_factory=lambda: {(): None})


async def _ensure_folder(
    session: AsyncSession,
    project_id: UUID,
    parts: tuple[str, ...],
    cache: _FolderCache,
    outcome: ImportOutcome,
) -> UUID | None:
    """Return the folder entity id for ``parts``, creating intermediates as needed."""
    key = tuple(p.lower() for p in parts)
    if key in cache.ids:
        return cache.ids[key]
    parent_id = await _ensure_folder(session, project_id, parts[:-1], cache, outcome)
    try:
        entity = await tree_service.create_entity(
            session, project_id, TreeEntityType.folder, parts[-1], parent_id
        )
        outcome.folders_created += 1
        folder_id: UUID | None = entity.id
    except tree_service.NameConflictError:
        # A sibling with this name (case-insensitive) already exists — reuse it.
        folder_id = await _find_child_folder(session, project_id, parent_id, parts[-1])
    cache.ids[key] = folder_id
    return folder_id


async def _find_child_folder(
    session: AsyncSession, project_id: UUID, parent_id: UUID | None, name: str
) -> UUID | None:
    from sqlalchemy import func, select

    from inkstave.db.models.tree_entity import TreeEntity

    stmt = select(TreeEntity.id).where(
        TreeEntity.project_id == project_id,
        TreeEntity.type == TreeEntityType.folder,
        func.lower(TreeEntity.name) == name.lower(),
    )
    if parent_id is None:
        stmt = stmt.where(TreeEntity.is_root.is_(False), TreeEntity.parent_id.isnot(None))
    else:
        stmt = stmt.where(TreeEntity.parent_id == parent_id)
    return (await session.execute(stmt)).scalars().first()


@dataclass
class _Reconstruction:
    """Running state while materialising a plan into the project tree."""

    outcome: ImportOutcome
    cache: _FolderCache = field(default_factory=_FolderCache)
    text_blobs: dict[tuple[str, ...], bytes] = field(default_factory=dict)
    doc_ids: dict[tuple[str, ...], UUID] = field(default_factory=dict)


async def _import_text(
    session: AsyncSession,
    project_id: UUID,
    parent_id: UUID | None,
    zf: zipfile.ZipFile,
    entry: PlannedEntry,
    settings: Settings,
    state: _Reconstruction,
) -> None:
    """Create one document from a text entry, or count it as skipped if oversized."""
    raw = await asyncio.to_thread(_read_member_bounded, zf, entry.zip_name, settings.import_max_file_bytes)
    content = decode_text(raw)
    if len(content.encode("utf-8")) > settings.max_document_bytes:
        state.outcome.skipped += 1
        return
    entity = await tree_service.create_entity(
        session, project_id, TreeEntityType.doc, entry.parts[-1], parent_id
    )
    await document_service.set_content_from_collab(session, entity.id, content)
    state.outcome.docs_created += 1
    state.text_blobs[entry.parts] = raw
    state.doc_ids[entry.parts] = entity.id


async def reconstruct_tree(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    zf: zipfile.ZipFile,
    plan: ImportPlan,
    *,
    settings: Settings,
) -> ImportOutcome:
    """Create folders/docs/files for the planned entries, reusing the services."""
    state = _Reconstruction(ImportOutcome(skipped=plan.skipped))

    for entry in plan.entries:
        parent_id = await _ensure_folder(session, project_id, entry.parts[:-1], state.cache, state.outcome)
        if entry.classification == "text":
            await _import_text(session, project_id, parent_id, zf, entry, settings, state)
            continue
        try:
            await _import_binary(session, store, (project_id, parent_id), zf, entry, settings)
            state.outcome.files_created += 1
        except _SkipEntryError:
            state.outcome.skipped += 1

    root = detect_root_doc(plan.entries, state.text_blobs)
    if root is not None and root in state.doc_ids:
        state.outcome.root_doc_entity_id = state.doc_ids[root]
        state.outcome.root_doc_path = root
    return state.outcome


class _SkipEntryError(Exception):
    """Internal: a binary entry could not be imported and is recorded as skipped."""


async def _import_binary(
    session: AsyncSession,
    store: ObjectStore,
    location: tuple[UUID, UUID | None],
    zf: zipfile.ZipFile,
    entry: PlannedEntry,
    settings: Settings,
) -> None:
    """Import one binary entry at ``location``, a ``(project_id, parent_id)`` pair."""
    project_id, parent_id = location
    name = entry.parts[-1]
    cap = min(settings.import_max_file_bytes, settings.max_upload_bytes)
    data = await asyncio.to_thread(_read_member_bounded, zf, entry.zip_name, cap)
    # Validate the sniffed type BEFORE creating any entity, so a rejected binary
    # leaves no orphan tree node behind.
    content_type = sniff_content_type(data[: settings.storage_stream_chunk_bytes], None)
    if content_type not in settings.allowed_upload_mime or not content_matches_extension(name, content_type):
        raise _SkipEntryError()

    pos = {"i": 0}

    async def reader(size: int) -> bytes:
        chunk = data[pos["i"] : pos["i"] + size]
        pos["i"] += len(chunk)
        return chunk

    try:
        await file_service.upload_file(
            session,
            store,
            project_id,
            parent_id,
            file_service.UploadSource(name, reader, content_type, name),
        )
    except (
        file_service.UnsupportedMediaTypeError,
        file_service.FileTooLargeError,
        tree_service.NameConflictError,
    ) as exc:
        raise _SkipEntryError() from exc
