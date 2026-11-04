"""Support for the Git integration tests (spec 121): dulwich's own HTTP client, driven into the ASGI app.

``Urllib3HttpGitClient`` takes a pool manager. ``AsgiPool`` answers its ``request`` calls by running the
app's request on the test's event loop, so the client runs in a worker thread (as in production, where
dulwich is synchronous) while the app stays in the test's transaction. No socket, no ``git`` binary.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from dulwich.client import Urllib3HttpGitClient
from dulwich.objects import ObjectID
from dulwich.refs import Ref
from dulwich.repo import Repo
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.infra.deps import get_object_store
from inkstave.infra.storage.local import LocalObjectStore
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User
from inkstave.modules.git.repo.repository import MAIN_REF
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.content.documents import set_content_from_collab
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.tree_entity import TreeEntityType
from inkstave.modules.projects.tree.service import create_entity
from tests.collab_ws_harness import install_collab
from tests.factories import UserFactory

API = "/api/v1"
BASE_HOST = "http://test"


class _Response:
    def __init__(self, response: Any) -> None:
        self.status = response.status_code
        self.headers = response.headers
        self._body = io.BytesIO(response.content)
        self._url = str(response.url)

    def read(self, amt: int | None = None) -> bytes:
        return self._body.read() if amt is None else self._body.read(amt)

    def geturl(self) -> str:
        return self._url

    def release_conn(self) -> None:
        return None

    def close(self) -> None:
        self._body.close()


class AsgiPool:
    """A stand-in for a urllib3 ``PoolManager`` that sends each request to the test's ASGI client."""

    def __init__(self, client: AsyncClient, loop: asyncio.AbstractEventLoop) -> None:
        self._client = client
        self._loop = loop
        self.headers: dict[str, str] = {}

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        body = kwargs.get("body")
        if body is not None and not isinstance(body, bytes):
            body = b"".join(body)
        coro = self._client.request(
            method, url.removeprefix(BASE_HOST), headers=kwargs.get("headers") or {}, content=body
        )
        return _Response(asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=60))


def git_client(
    client: AsyncClient, token: str | None, loop: asyncio.AbstractEventLoop
) -> Urllib3HttpGitClient:
    """A dulwich client for the Git URL, authenticated with ``token`` as the password (or none)."""
    pool = AsgiPool(client, loop)
    return Urllib3HttpGitClient(
        BASE_HOST, pool_manager=pool, username="git" if token else None, password=token
    )


def repo_path_for(project_id: UUID) -> str:
    return f"/api/v1/git/projects/{project_id}.git"


def _clone_sync(
    client: AsyncClient,
    token: str | None,
    project_id: UUID,
    target: Path,
    loop: asyncio.AbstractEventLoop,
) -> Repo:
    repo = Repo.init(str(target), mkdir=True)
    result = git_client(client, token, loop).fetch(repo_path_for(project_id).encode(), repo)
    repo.refs[MAIN_REF] = result.refs[MAIN_REF]
    repo.refs.set_symbolic_ref(Ref(b"HEAD"), MAIN_REF)
    return repo


async def clone_into(client: AsyncClient, token: str | None, project_id: UUID, target: Path) -> Repo:
    """Fetch ``main`` into a new local repository at ``target``, the way ``git clone`` does."""
    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(_clone_sync, client, token, project_id, target, loop)


def _push_sync(
    client: AsyncClient,
    token: str | None,
    project_id: UUID,
    local: Repo,
    loop: asyncio.AbstractEventLoop,
) -> Any:
    new_sha = local.refs[MAIN_REF]

    def update_refs(refs: dict[Ref, ObjectID]) -> dict[Ref, ObjectID]:
        return {MAIN_REF: ObjectID(new_sha)}

    def pack(have: Any, want: Any, **kwargs: Any) -> Any:
        return local.object_store.generate_pack_data(set(have), set(want), **kwargs)

    return git_client(client, token, loop).send_pack(
        repo_path_for(project_id).encode(), update_refs, generate_pack_data=pack
    )


async def push_main(client: AsyncClient, token: str | None, project_id: UUID, local: Repo) -> Any:
    """Push the local ``main`` to the project. Returns dulwich's ``SendPackResult``."""
    loop = asyncio.get_running_loop()
    return await asyncio.to_thread(_push_sync, client, token, project_id, local, loop)


def commit_all(repo: Repo, message: bytes = b"local work") -> bytes:
    """Commit every file of the working tree to ``main`` (the repo is non-bare with a worktree)."""
    from dulwich.objects import Blob, Commit, Tree

    root = Tree()
    work = Path(repo.path)
    for path in sorted(p for p in work.rglob("*") if p.is_file() and ".git" not in p.parts):
        blob = Blob.from_string(path.read_bytes())
        repo.object_store.add_object(blob)
        root.add(path.relative_to(work).as_posix().encode(), 0o100644, blob.id)
    repo.object_store.add_object(root)
    commit = Commit()
    commit.tree = root.id
    commit.parents = [repo.refs[MAIN_REF]] if MAIN_REF in repo.refs else []
    commit.author = commit.committer = b"Writer <writer@example.test>"
    commit.author_time = commit.commit_time = 1_700_000_000
    commit.author_timezone = commit.commit_timezone = 0
    commit.encoding = b"UTF-8"
    commit.message = message
    repo.object_store.add_object(commit)
    repo.refs[MAIN_REF] = commit.id
    return commit.id


@dataclass
class GitWorld:
    project_id: UUID
    owner_id: UUID
    owner_token: str  # the owner's Git access token
    viewer_token: str
    stranger_token: str
    doc_id: UUID
    store: LocalObjectStore


async def _member(db_session: AsyncSession, project_id: UUID, role: MembershipRole) -> User:
    user = await UserFactory.create(db_session)
    db_session.add(
        ProjectMembership(project_id=project_id, user_id=user.id, role=role, status=MembershipStatus.active)
    )
    await db_session.commit()
    return user


async def git_token_for(client: AsyncClient, user: User) -> str:
    jwt, _ = build_token_service(get_settings()).create_access_token(user)
    response = await client.post(
        f"{API}/git/tokens", json={"name": "laptop"}, headers={"Authorization": f"Bearer {jwt}"}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["token"])


async def provision_world(
    app: Any, client: AsyncClient, db_session: AsyncSession, redis: Any, tmp_path: Path
) -> GitWorld:
    """A project with one document, an owner, a viewer and a stranger, all with Git tokens."""
    install_collab(app, db_session, redis, collab_text_flush_debounce_ms=10_000_000)
    store = LocalObjectStore(tmp_path / "blobs", 65536)
    app.dependency_overrides[get_object_store] = lambda: store
    owner = await UserFactory.create(db_session)
    await db_session.commit()
    project = await create_project(db_session, owner.id, "Thesis")
    entity = await create_entity(db_session, project.id, TreeEntityType.doc, "main.tex", None)
    await set_content_from_collab(db_session, entity.id, "\\documentclass{article}\nalpha\n")
    await db_session.commit()
    viewer = await _member(db_session, project.id, MembershipRole.viewer)
    stranger = await UserFactory.create(db_session)
    await db_session.commit()
    return GitWorld(
        project_id=project.id,
        owner_id=owner.id,
        owner_token=await git_token_for(client, owner),
        viewer_token=await git_token_for(client, viewer),
        stranger_token=await git_token_for(client, stranger),
        doc_id=entity.id,
        store=store,
    )


@pytest.fixture
def git_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Turn Git on for one test, with its repositories in a temporary directory."""
    root = tmp_path / "git-repos"
    monkeypatch.setenv("GIT_ENABLED", "true")
    monkeypatch.setenv("GIT_REPOS_ROOT", str(root))
    get_settings.cache_clear()
    return root


@pytest_asyncio.fixture
async def world(
    git_enabled: Path,
    app: Any,
    async_client: AsyncClient,
    db_session: AsyncSession,
    redis: Any,
    tmp_path: Path,
) -> GitWorld:
    return await provision_world(app, async_client, db_session, redis, tmp_path)


async def document_text(db_session: AsyncSession, doc_id: UUID) -> str:
    from inkstave.modules.projects.models.document import Document

    row = await db_session.scalar(select(Document.content).where(Document.entity_id == doc_id))
    return str(row)


async def entity_ids_by_name(db_session: AsyncSession, project_id: UUID) -> dict[str, UUID]:
    from inkstave.modules.projects.models.tree_entity import TreeEntity

    rows = await db_session.execute(
        select(TreeEntity.name, TreeEntity.id).where(TreeEntity.project_id == project_id)
    )
    return dict(rows.all())
