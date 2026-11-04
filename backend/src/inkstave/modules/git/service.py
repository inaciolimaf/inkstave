"""Git operations on a project: advertise, fetch and push (spec 121 §3, §5.2–5.4).

Every repository operation runs under the project's Redis lock with one deadline
(``GIT_OPERATION_TIMEOUT_S``) and in a thread, because dulwich is synchronous. Database work uses short
sessions from the session factory and commits them itself: the request session commits only when the route
returns, and a push must write its tree before its live text. The order of effects in a push is fixed: the
project tree commits, then the live documents change, then ``main`` moves, then ``git_repo_state`` records
it. A failure before the tree commit changes nothing, and one after it is reconciled by the next snapshot.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from dulwich.objects import ObjectID
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.git.lock import project_git_lock
from inkstave.modules.git.push.apply import Applied, PushApplyError, apply_changes, delete_blobs
from inkstave.modules.git.push.live import apply_live_texts
from inkstave.modules.git.push.receive import PreparedPush, prepare_push
from inkstave.modules.git.repo.protocol import advertise, progress_lines, report_lines, run_upload_pack
from inkstave.modules.git.repo.repository import MAIN_REF, open_or_create, repo_dir
from inkstave.modules.git.repo.snapshot import record_head, snapshot_locked

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.collab.ws.components import CollabComponents
    from inkstave.modules.git.auth.access import GitCaller

logger = logging.getLogger("inkstave.git")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True, slots=True)
class GitDeps:
    factory: SessionFactory
    store: ObjectStore
    collab: CollabComponents | None
    settings: Settings
    redis: Redis


def _repo_path(deps: GitDeps, project_id: UUID) -> Path:
    return repo_dir(deps.settings.git_repos_root, project_id)


async def _snapshot(deps: GitDeps, project_id: UUID) -> str:
    return await snapshot_locked(
        factory=deps.factory,
        store=deps.store,
        collab=deps.collab,
        settings=deps.settings,
        project_id=project_id,
    )


async def advertise_refs(deps: GitDeps, project_id: UUID, service: str) -> bytes:
    """``info/refs`` for either service. The project is snapshotted first, so ``main`` is current."""
    timeout = deps.settings.git_operation_timeout_s
    async with project_git_lock(deps.redis, project_id, timeout), asyncio.timeout(timeout):
        await _snapshot(deps, project_id)
        return await asyncio.to_thread(advertise, _repo_path(deps, project_id), service)


async def upload_pack(deps: GitDeps, project_id: UUID, body: bytes) -> bytes:
    timeout = deps.settings.git_operation_timeout_s
    async with project_git_lock(deps.redis, project_id, timeout), asyncio.timeout(timeout):
        return await asyncio.to_thread(run_upload_pack, _repo_path(deps, project_id), body)


async def receive_pack(deps: GitDeps, project_id: UUID, body: bytes, caller: GitCaller) -> bytes:
    """Apply one push, or refuse it whole. Returns the ``report-status`` body for the client."""
    timeout = deps.settings.git_operation_timeout_s
    async with project_git_lock(deps.redis, project_id, timeout), asyncio.timeout(timeout):
        head = await _snapshot(deps, project_id)
        prepared = await asyncio.to_thread(prepare_push, _repo_path(deps, project_id), body, deps.settings)
        if not prepared.accepted or prepared.new is None:
            return _reply(prepared, [])
        warnings: list[str] | None = []
        if prepared.new.decode("ascii") != head:
            warnings = await _apply(deps, project_id, caller, prepared)
        if warnings is None:
            return _reply(prepared, [])
        await _move_main(deps, project_id, prepared, head)
        return _reply(prepared, warnings)


def _reply(prepared: PreparedPush, warnings: list[str]) -> bytes:
    """The response: messages on side-band channel 2, then the report on channel 1."""
    caps = prepared.capabilities
    refs = prepared.refs or [MAIN_REF]
    if prepared.unpack_error is not None:
        report = report_lines(caps, prepared.unpack_error, [(ref, "unpack failed") for ref in refs])
        return progress_lines(caps, [prepared.unpack_error]) + report
    if prepared.refusal is not None:
        report = report_lines(caps, "ok", [(ref, prepared.refusal) for ref in refs])
        return progress_lines(caps, prepared.messages or [prepared.refusal]) + report
    report = report_lines(caps, "ok", [(ref, "ok") for ref in refs])
    return progress_lines(caps, warnings) + report


async def _apply(
    deps: GitDeps, project_id: UUID, caller: GitCaller, prepared: PreparedPush
) -> list[str] | None:
    """Steps 2 and 3 of a push: the tree, committed, then the live text.

    Returns the conflict warnings, or ``None`` when the project refuses the push (the reason is set).
    """
    applied = Applied()
    try:
        async with deps.factory() as session:
            await apply_changes(session, deps.store, project_id, prepared.changes, deps.settings, applied)
            await session.commit()
    except PushApplyError as exc:
        await delete_blobs(deps.store, applied.new_keys)
        prepared.refusal = str(exc)
        prepared.messages = [str(exc)]
        return None
    except BaseException:
        await delete_blobs(deps.store, applied.new_keys)
        raise
    await delete_blobs(deps.store, applied.obsolete_keys)
    if deps.collab is None or not applied.texts:
        return []
    return await apply_live_texts(
        deps.collab, project_id=project_id, author_id=caller.user.id, targets=applied.texts
    )


async def _move_main(deps: GitDeps, project_id: UUID, prepared: PreparedPush, head: str) -> None:
    """Step 4: move ``main`` to the pushed commit, record it, and write the audit line."""
    new_sha = prepared.new.decode("ascii") if prepared.new is not None else head
    if new_sha != head:
        await asyncio.to_thread(_set_main, _repo_path(deps, project_id), head, new_sha)
    async with deps.factory() as session:
        await record_head(session, project_id, new_sha)
        await session.commit()
    logger.info("git push accepted project=%s commit=%s", project_id, new_sha)


def _set_main(path: Path, old_sha: str, new_sha: str) -> None:
    with open_or_create(path) as repo:
        repo.refs.set_if_equals(
            MAIN_REF, ObjectID(old_sha.encode("ascii")), ObjectID(new_sha.encode("ascii"))
        )
