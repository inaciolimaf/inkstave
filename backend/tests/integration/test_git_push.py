"""Spec 121 §7 AC2–AC5 and §9: pushes apply through the CRDT, refuse whole, and keep identity on rename."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

import pytest
from dulwich.errors import SendPackError
from dulwich.objects import Blob, Commit, ObjectID, Tree
from dulwich.refs import Ref
from dulwich.repo import Repo
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.git.lock import GitBusyError, project_git_lock
from inkstave.modules.git.push.apply import TextTarget
from inkstave.modules.git.push.live import apply_live_texts
from inkstave.modules.git.repo.repository import MAIN_REF
from inkstave.modules.history.models import HistoryUpdate
from tests.integration._git_support import (
    GitWorld,
    clone_into,
    document_text,
    entity_ids_by_name,
    git_client,
    git_enabled,
    push_main,
    repo_path_for,
    world,
)

pytestmark = pytest.mark.integration

__all__ = ["git_enabled", "world"]  # the fixtures this module uses, re-exported for pytest

_BASE = "\\documentclass{article}\nalpha\n"


def _commit(repo: Repo, files: dict[bytes, bytes], parents: list[ObjectID], ref: Ref = MAIN_REF) -> ObjectID:
    """A commit whose tree is exactly ``files``. Names are taken as they are, even ``..``."""
    root = Tree()
    for name, data in files.items():
        blob = Blob.from_string(data)
        repo.object_store.add_object(blob)
        root.add(name, 0o100644, blob.id)
    repo.object_store.add_object(root)
    commit = Commit()
    commit.tree = root.id
    commit.parents = parents
    commit.author = commit.committer = b"Writer <writer@example.test>"
    commit.author_time = commit.commit_time = 1_700_000_000
    commit.author_timezone = commit.commit_timezone = 0
    commit.encoding = b"UTF-8"
    commit.message = b"local work\n"
    repo.object_store.add_object(commit)
    repo.refs[ref] = commit.id
    return commit.id


def _files_of(repo: Repo) -> dict[bytes, bytes]:
    tree = repo[repo[repo.refs[MAIN_REF]].tree]
    return {entry.path: bytes(repo[entry.sha].data) for entry in tree.items()}


async def _clone(client: AsyncClient, world: GitWorld, target: Path) -> Repo:
    return await clone_into(client, world.owner_token, world.project_id, target)


async def _push_ref(client: AsyncClient, world: GitWorld, local: Repo, ref: bytes) -> dict[bytes, Any]:
    """Push the local commit that ``ref`` names to the same-named ref on the server."""
    loop = asyncio.get_running_loop()

    def run() -> Any:
        sha = local.refs[Ref(ref)]

        def update(_: dict[Ref, ObjectID]) -> dict[Ref, ObjectID]:
            return {Ref(ref): ObjectID(sha)}

        return git_client(client, world.owner_token, loop).send_pack(
            repo_path_for(world.project_id).encode(),
            update,
            generate_pack_data=lambda have, want, **kw: local.object_store.generate_pack_data(
                set(have), set(want), **kw
            ),
        )

    result = await asyncio.to_thread(run)
    return dict(result.ref_status or {})


async def test_push_applies_through_crdt(
    world: GitWorld, app: Any, async_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"main.tex"] = b"\\documentclass{article}\nalpha\nbeta from the laptop\n"
    _commit(local, files, [local.refs[MAIN_REF]])

    status = await push_main(async_client, world.owner_token, world.project_id, local)
    assert (status.ref_status or {})[MAIN_REF] is None

    expected = "\\documentclass{article}\nalpha\nbeta from the laptop\n"
    assert await app.state.collab.manager.current_text(world.doc_id) == expected
    assert await document_text(db_session, world.doc_id) == expected
    latest = await db_session.execute(
        select(HistoryUpdate.author_id, HistoryUpdate.origin)
        .where(HistoryUpdate.doc_id == world.doc_id)
        .order_by(HistoryUpdate.version.desc())
        .limit(1)
    )
    assert latest.one() == (world.owner_id, "git-push")


async def test_the_next_fetch_after_a_push_adds_no_commit(
    world: GitWorld, async_client: AsyncClient, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"main.tex"] = b"pushed\n"
    pushed = _commit(local, files, [local.refs[MAIN_REF]])
    await push_main(async_client, world.owner_token, world.project_id, local)
    again = await _clone(async_client, world, tmp_path / "again")
    assert again.refs[MAIN_REF] == pushed


async def test_non_fast_forward_refused(
    world: GitWorld, app: Any, async_client: AsyncClient, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    await app.state.collab.manager.apply_server_update(world.doc_id, "web edit\n", "browser")
    files = _files_of(local)
    files[b"main.tex"] = b"laptop edit\n"
    _commit(local, files, [local.refs[MAIN_REF]])

    status = await push_main(async_client, world.owner_token, world.project_id, local)
    reason = str((status.ref_status or {})[MAIN_REF])
    assert "Pull first: the project changed in Inkstave." in reason
    assert await app.state.collab.manager.current_text(world.doc_id) == "web edit\n"


async def test_after_a_pull_the_same_change_is_accepted(
    world: GitWorld, app: Any, async_client: AsyncClient, tmp_path: Path
) -> None:
    await app.state.collab.manager.apply_server_update(world.doc_id, "web edit\n", "browser")
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"main.tex"] = b"web edit\nlaptop line\n"
    _commit(local, files, [local.refs[MAIN_REF]])
    status = await push_main(async_client, world.owner_token, world.project_id, local)
    assert (status.ref_status or {})[MAIN_REF] is None
    assert await app.state.collab.manager.current_text(world.doc_id) == "web edit\nlaptop line\n"


async def test_a_rename_keeps_the_entity_identity(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"thesis.tex"] = files.pop(b"main.tex")
    _commit(local, files, [local.refs[MAIN_REF]])
    status = await push_main(async_client, world.owner_token, world.project_id, local)
    assert (status.ref_status or {})[MAIN_REF] is None
    ids = await entity_ids_by_name(db_session, world.project_id)
    assert "main.tex" not in ids
    assert ids["thesis.tex"] == world.doc_id


async def test_invalid_push_changes_nothing(
    world: GitWorld, app: Any, async_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    before = await entity_ids_by_name(db_session, world.project_id)
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"main.tex"] = b"changed but refused\n"
    files[b"extra.exe"] = b"MZ\x00\x00binary"
    _commit(local, files, [local.refs[MAIN_REF]])

    status = await push_main(async_client, world.owner_token, world.project_id, local)
    reason = str((status.ref_status or {})[MAIN_REF])
    assert "extra.exe: this file type is not allowed" in reason
    assert await entity_ids_by_name(db_session, world.project_id) == before
    assert await document_text(db_session, world.doc_id) == _BASE
    assert await app.state.collab.manager.current_text(world.doc_id) == _BASE


async def test_a_traversal_name_refuses_the_whole_push(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    files[b"main.tex"] = b"should not land\n"
    files[b".."] = b"not a directory\n"
    _commit(local, files, [local.refs[MAIN_REF]])
    status = await push_main(async_client, world.owner_token, world.project_id, local)
    reason = str((status.ref_status or {})[MAIN_REF])
    assert "path-traversal segment" in reason
    assert await document_text(db_session, world.doc_id) == _BASE


async def test_a_push_to_another_branch_is_refused(
    world: GitWorld, async_client: AsyncClient, tmp_path: Path
) -> None:
    local = await _clone(async_client, world, tmp_path / "work")
    _commit(local, _files_of(local), [local.refs[MAIN_REF]], ref=Ref(b"refs/heads/topic"))
    status = await _push_ref(async_client, world, local, b"refs/heads/topic")
    assert "Only refs/heads/main can be pushed." in str(status[Ref(b"refs/heads/topic")])


async def test_a_push_larger_than_the_cap_is_refused(
    world: GitWorld, async_client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_MAX_PUSH_BYTES", "2000")
    get_settings.cache_clear()
    local = await _clone(async_client, world, tmp_path / "work")
    files = _files_of(local)
    # Incompressible bytes, so the pack really is larger than the cap.
    noise = random.Random(121).getrandbits(8 * 5000).to_bytes(5000, "big")
    files[b"big.png"] = b"\x89PNG\r\n\x1a\n" + noise
    _commit(local, files, [local.refs[MAIN_REF]])
    # dulwich enforces the pack cap while ingesting and reports it as an unpack error (git's own behaviour).
    with pytest.raises(SendPackError, match="exceeds maximum input size"):
        await push_main(async_client, world.owner_token, world.project_id, local)


async def test_a_second_push_waits_for_the_first_on_the_same_project(world: GitWorld, redis: Any) -> None:
    order: list[str] = []

    async def first() -> None:
        async with project_git_lock(redis, world.project_id, 5):
            order.append("first in")
            await asyncio.sleep(0.2)
            order.append("first out")

    async def second() -> None:
        await asyncio.sleep(0.05)
        async with project_git_lock(redis, world.project_id, 5):
            order.append("second in")

    await asyncio.gather(first(), second())
    assert order == ["first in", "first out", "second in"]


async def test_a_waiter_gives_up_at_its_deadline(world: GitWorld, redis: Any) -> None:
    async with project_git_lock(redis, world.project_id, 5):
        with pytest.raises(GitBusyError):
            async with project_git_lock(redis, world.project_id, 0.1):
                pass


async def test_a_conflicting_region_is_replaced_and_reported(world: GitWorld, app: Any) -> None:
    comp = app.state.collab
    await comp.manager.apply_server_update(world.doc_id, "keep\ncollaborator\n", "browser")
    warnings = await apply_live_texts(
        comp,
        project_id=world.project_id,
        author_id=world.owner_id,
        targets=[
            TextTarget(doc_id=world.doc_id, path=("main.tex",), old="keep\nshared\n", new="keep\npushed\n")
        ],
    )
    assert await comp.manager.current_text(world.doc_id) == "keep\npushed\n"
    assert warnings == ["main.tex: lines 2–2 were also edited in Inkstave; the pushed version was kept"]
