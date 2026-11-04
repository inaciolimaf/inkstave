"""Apply an accepted push to the project tree, inside the caller's transaction (spec 121 §5.4 step 2).

Tree operations go through the projects services, so names, folders and sibling rules are the same as in
the web app. Text documents are not written here: their new text reaches the live document as CRDT edits
after this transaction commits (``live.apply_live_texts``), because the CRDT rows reference the document rows.
Binary blobs are written before the commit; the blobs they replace are deleted only after it.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, select

from inkstave.core.errors import AppError
from inkstave.infra.storage.base import ObjectStore
from inkstave.modules.git.push.changes import FileWrite, PushChanges, kind_of
from inkstave.modules.git.repo.snapshot import Path, path_index
from inkstave.modules.projects import (
    File,
    TreeEntity,
    TreeEntityType,
    create_entity,
    get_tree,
    move_entity,
    rename_entity,
)
from inkstave.modules.projects.content.documents import read_content_for_collab
from inkstave.modules.projects.content.files import ByteReader, UploadSource, upload_file
from inkstave.modules.projects.tree.service import ensure_root

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings


class PushApplyError(AppError):
    """The push cannot be applied to the project as it is now. Nothing is written."""

    status_code = 409
    error_type = "push_conflict"


@dataclass(frozen=True, slots=True)
class TextTarget:
    """A document whose text must become ``new``; ``old`` is what the pushed base had."""

    doc_id: UUID
    path: Path
    old: str
    new: str


@dataclass(slots=True)
class Applied:
    texts: list[TextTarget] = field(default_factory=list)
    obsolete_keys: list[str] = field(default_factory=list)  # blobs to delete after the commit
    new_keys: list[str] = field(default_factory=list)  # blobs written here, to delete if the commit fails


def _byte_reader(data: bytes) -> ByteReader:
    position = 0

    async def read(size: int) -> bytes:
        nonlocal position
        chunk = data[position : position + size]
        position += len(chunk)
        return chunk

    return read


async def _ensure_folder(
    session: AsyncSession, project_id: UUID, parts: Path, paths: dict[Path, TreeEntity]
) -> UUID:
    """The id of the folder at ``parts``, creating it and its missing parents. The root for ``()``."""
    if not parts:
        return (await ensure_root(session, project_id)).id
    existing = paths.get(parts)
    if existing is not None:
        if existing.type is not TreeEntityType.folder:
            raise PushApplyError(f"{'/'.join(parts)} is a document or file in Inkstave, not a folder.")
        return existing.id
    parent_id = await _ensure_folder(session, project_id, parts[:-1], paths)
    folder = await create_entity(session, project_id, TreeEntityType.folder, parts[-1], parent_id)
    paths[parts] = folder
    return folder.id


async def _detach(
    session: AsyncSession,
    project_id: UUID,
    entity: TreeEntity,
    paths: dict[Path, TreeEntity],
    applied: Applied,
) -> None:
    """Remove an entity and its row, keeping its blob until the commit has succeeded."""
    keys = await session.scalars(select(File.storage_key).where(File.entity_id == entity.id))
    applied.obsolete_keys.extend(keys)
    await session.execute(
        delete(TreeEntity).where(TreeEntity.id == entity.id, TreeEntity.project_id == project_id)
    )
    await session.flush()
    for parts in [p for p, e in paths.items() if e.id == entity.id]:
        del paths[parts]


async def _delete_path(
    session: AsyncSession, project_id: UUID, parts: Path, paths: dict[Path, TreeEntity], applied: Applied
) -> None:
    entity = paths.get(parts)
    if entity is None or entity.type is TreeEntityType.folder:
        return  # already gone, or a folder: git does not track folders, so nothing to remove
    await _detach(session, project_id, entity, paths, applied)


async def _rename_path(
    session: AsyncSession,
    project_id: UUID,
    old: Path,
    new: Path,
    paths: dict[Path, TreeEntity],
) -> None:
    entity = paths.get(old)
    if entity is None or entity.is_root:
        return  # the project no longer holds the old path; the new one is written as an addition
    if entity.name != new[-1]:
        entity = await rename_entity(session, project_id, entity.id, new[-1])
    parent_id = await _ensure_folder(session, project_id, new[:-1], paths)
    if entity.parent_id != parent_id:
        entity = await move_entity(session, project_id, entity.id, parent_id)
    del paths[old]
    paths[new] = entity


async def _write_text(
    session: AsyncSession,
    project_id: UUID,
    write: FileWrite,
    paths: dict[Path, TreeEntity],
    applied: Applied,
) -> None:
    text = write.data.decode("utf-8")
    old_text = None if write.old is None else write.old.decode("utf-8", errors="replace")
    entity = paths.get(write.parts)
    if entity is None or entity.type is not TreeEntityType.doc:
        if entity is not None:
            await _detach(session, project_id, entity, paths, applied)
        parent_id = await _ensure_folder(session, project_id, write.parts[:-1], paths)
        entity = await create_entity(session, project_id, TreeEntityType.doc, write.parts[-1], parent_id)
        paths[write.parts] = entity
    if old_text is None:
        old_text = await read_content_for_collab(session, entity.id)
    applied.texts.append(TextTarget(entity.id, write.parts, old_text, text))


async def _write_binary(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    write: FileWrite,
    paths: dict[Path, TreeEntity],
    applied: Applied,
) -> None:
    entity = paths.get(write.parts)
    if entity is not None:
        await _detach(session, project_id, entity, paths, applied)
    parent_id = await _ensure_folder(session, project_id, write.parts[:-1], paths)
    name = write.parts[-1]
    declared = mimetypes.guess_type(name)[0]
    row = await upload_file(
        session,
        store,
        project_id,
        parent_id,
        UploadSource(name, _byte_reader(write.data), declared, name),
    )
    applied.new_keys.append(row.storage_key)
    paths[write.parts] = row.entity


async def _write_one(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    write: FileWrite,
    paths: dict[Path, TreeEntity],
    settings: Settings,
    applied: Applied,
) -> None:
    if kind_of(write.parts[-1], settings) == "text":
        await _write_text(session, project_id, write, paths, applied)
    else:
        await _write_binary(session, store, project_id, write, paths, applied)


async def apply_changes(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    changes: PushChanges,
    settings: Settings,
    applied: Applied,
) -> None:
    """Make the project's tree match the pushed tree. ``applied`` collects what the caller must clean up."""
    paths = path_index(await get_tree(session, project_id))
    for parts in changes.deletes:
        await _delete_path(session, project_id, parts, paths, applied)
    for old, new in changes.renames:
        await _rename_path(session, project_id, old, new, paths)
    for write in changes.writes:
        await _write_one(session, store, project_id, write, paths, settings, applied)


async def delete_blobs(store: ObjectStore, keys: list[str]) -> None:
    for key in keys:
        await store.delete(key)
