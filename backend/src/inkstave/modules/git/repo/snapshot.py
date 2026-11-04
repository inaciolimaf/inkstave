"""Snapshot: commit the live project to ``main`` before a fetch or a push (spec 121 §3).

Open CRDT rooms are flushed first, so documents carry their live text. The tree is read from the database
and the blob store, then committed by ``repository.snapshot_commit`` in a thread. ``git_repo_state.head``
records the result.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from inkstave.infra.storage.base import ObjectNotFoundError
from inkstave.modules.collab import flush_open_project_docs
from inkstave.modules.git.models import GitRepoState
from inkstave.modules.git.repo.repository import repo_dir, snapshot_commit
from inkstave.modules.projects import Document, File, TreeEntity, TreeEntityType, get_tree

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.collab.ws.components import CollabComponents

    SessionFactory = Callable[[], Any]
Path = tuple[str, ...]

logger = logging.getLogger(__name__)


def path_index(entities: Sequence[TreeEntity]) -> dict[Path, TreeEntity]:
    """Every non-root entity keyed by its path as name segments. Orphans are skipped."""
    by_id = {entity.id: entity for entity in entities}
    cache: dict[UUID, Path | None] = {}

    def parts_of(entity: TreeEntity) -> Path | None:
        if entity.id in cache:
            return cache[entity.id]
        if entity.is_root:
            cache[entity.id] = ()
            return ()
        parent = by_id.get(entity.parent_id) if entity.parent_id is not None else None
        parent_parts = parts_of(parent) if parent is not None else None
        result = None if parent_parts is None else (*parent_parts, entity.name)
        cache[entity.id] = result
        return result

    index: dict[Path, TreeEntity] = {}
    for entity in entities:
        parts = parts_of(entity)
        if parts:
            index[parts] = entity
    return index


async def _read_blob(store: ObjectStore, key: str) -> bytes | None:
    try:
        _, stream = await store.open(key)
    except ObjectNotFoundError:
        logger.warning("git snapshot: blob %s is missing; the file is left out", key)
        return None
    return b"".join([chunk async for chunk in stream])


async def read_project_files(
    session: AsyncSession, store: ObjectStore, project_id: UUID
) -> list[tuple[Path, bytes]]:
    """The bytes of every document and file of the project, keyed by path."""
    entities = await get_tree(session, project_id)
    index = path_index(entities)
    doc_rows = await session.execute(
        select(Document.entity_id, Document.content).where(Document.project_id == project_id)
    )
    contents: dict[UUID, str] = dict(doc_rows.tuples().all())
    file_rows = await session.execute(
        select(File.entity_id, File.storage_key).where(File.project_id == project_id)
    )
    keys: dict[UUID, str] = dict(file_rows.tuples().all())
    files: list[tuple[Path, bytes]] = []
    for parts, entity in index.items():
        if entity.type is TreeEntityType.doc:
            files.append((parts, contents.get(entity.id, "").encode("utf-8")))
        elif entity.type is TreeEntityType.file and entity.id in keys:
            data = await _read_blob(store, keys[entity.id])
            if data is not None:
                files.append((parts, data))
    return files


async def record_head(session: AsyncSession, project_id: UUID, head: str) -> None:
    """Store what ``main`` now points to (``git_repo_state``)."""
    row = await session.get(GitRepoState, project_id)
    if row is None:
        session.add(GitRepoState(project_id=project_id, head=head))
    else:
        row.head = head
        row.updated_at = func.now()
    await session.flush()


async def snapshot_locked(
    *,
    factory: SessionFactory,
    store: ObjectStore,
    collab: CollabComponents | None,
    settings: Settings,
    project_id: UUID,
) -> str:
    """Commit the project's current state to ``main``. The caller holds the project's Git lock."""
    async with factory() as session:
        await flush_open_project_docs(collab, session, project_id)
        files = await read_project_files(session, store, project_id)
    head = await asyncio.to_thread(snapshot_commit, repo_dir(settings.git_repos_root, project_id), files)
    async with factory() as session:
        await record_head(session, project_id, head)
        await session.commit()
    return head
