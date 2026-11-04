"""Spec 121 §7 AC1, AC6, AC7 and §8: clone, roles, tokens and the feature switch, over Smart HTTP."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User
from inkstave.modules.git.models import GitAccessToken
from inkstave.modules.git.repo.repository import MAIN_REF
from tests.integration._git_support import GitWorld, clone_into, git_enabled, repo_path_for, world

pytestmark = pytest.mark.integration

__all__ = ["git_enabled", "world"]  # the fixtures this module uses, re-exported for pytest


def _basic(password: str) -> dict[str, str]:
    return {"Authorization": "Basic " + base64.b64encode(f"git:{password}".encode()).decode()}


def _advertise_url(world: GitWorld, service: str) -> tuple[str, dict[str, str]]:
    return f"{repo_path_for(world.project_id)}/info/refs", {"service": service}


def _main_blob(repo: Any, name: bytes) -> bytes:
    tree = repo[repo.refs[MAIN_REF]].tree
    for entry in repo[tree].items():
        if entry.path == name:
            return bytes(repo[entry.sha].data)
    raise AssertionError(f"{name!r} is not in main")


async def test_clone_gets_the_current_files_including_a_fresh_web_edit(
    world: GitWorld, app: Any, async_client: AsyncClient, tmp_path: Path
) -> None:
    # An edit still only in the live room (not yet in documents.content) reaches the clone.
    await app.state.collab.manager.apply_server_update(
        world.doc_id, "\\documentclass{article}\nbeta\n", "browser"
    )
    repo = await clone_into(async_client, world.owner_token, world.project_id, tmp_path / "c")
    assert _main_blob(repo, b"main.tex") == b"\\documentclass{article}\nbeta\n"


async def test_repeated_advertisements_of_an_unchanged_project_show_the_same_main(
    world: GitWorld, async_client: AsyncClient
) -> None:
    heads = []
    for _ in range(2):
        url, params = _advertise_url(world, "git-upload-pack")
        response = await async_client.get(url, params=params, headers=_basic(world.owner_token))
        assert response.status_code == 200
        heads.append(_main_line(response.content))
    assert heads[0] == heads[1]


def _main_line(body: bytes) -> bytes:
    for line in body.split(b"\n"):
        if b"refs/heads/main" in line:
            return line[4:44]
    raise AssertionError("main is not advertised")


async def test_viewer_can_clone_but_not_push(world: GitWorld, async_client: AsyncClient) -> None:
    url, params = _advertise_url(world, "git-upload-pack")
    read = await async_client.get(url, params=params, headers=_basic(world.viewer_token))
    assert read.status_code == 200
    url, params = _advertise_url(world, "git-receive-pack")
    write = await async_client.get(url, params=params, headers=_basic(world.viewer_token))
    assert write.status_code == 403
    assert write.json()["error"]["type"] == "insufficient_role"


async def test_a_stranger_gets_404_and_no_token_gets_401_with_a_basic_challenge(
    world: GitWorld, async_client: AsyncClient
) -> None:
    url, params = _advertise_url(world, "git-upload-pack")
    stranger = await async_client.get(url, params=params, headers=_basic(world.stranger_token))
    assert stranger.status_code == 404
    anonymous = await async_client.get(url, params=params)
    assert anonymous.status_code == 401
    assert anonymous.headers["www-authenticate"] == 'Basic realm="Inkstave"'


async def test_a_revoked_token_gets_401(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    row = await db_session.scalar(select(GitAccessToken).where(GitAccessToken.user_id == world.owner_id))
    assert row is not None
    row.revoked_at = func.now()
    await db_session.flush()
    url, params = _advertise_url(world, "git-upload-pack")
    response = await async_client.get(url, params=params, headers=_basic(world.owner_token))
    assert response.status_code == 401


async def test_a_session_jwt_is_not_accepted_on_git_routes(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await db_session.get(User, world.owner_id)
    assert owner is not None
    jwt, _ = build_token_service(get_settings()).create_access_token(owner)
    url, params = _advertise_url(world, "git-upload-pack")
    as_basic = await async_client.get(url, params=params, headers=_basic(jwt))
    assert as_basic.status_code == 401
    as_bearer = await async_client.get(url, params=params, headers={"Authorization": f"Bearer {jwt}"})
    assert as_bearer.status_code == 401


async def test_git_token_rejected_on_api(world: GitWorld, async_client: AsyncClient) -> None:
    response = await async_client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {world.owner_token}"}
    )
    assert response.status_code == 401


async def test_git_disabled_404(
    world: GitWorld, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_ENABLED", "false")
    get_settings.cache_clear()
    url, params = _advertise_url(world, "git-upload-pack")
    response = await async_client.get(url, params=params, headers=_basic(world.owner_token))
    assert response.status_code == 404
    assert (await async_client.get("/api/v1/config")).json() == {"git_enabled": False}


async def test_the_flag_is_on_when_git_is_enabled(world: GitWorld, async_client: AsyncClient) -> None:
    assert (await async_client.get("/api/v1/config")).json() == {"git_enabled": True}


async def test_the_dumb_protocol_is_not_served(world: GitWorld, async_client: AsyncClient) -> None:
    response = await async_client.get(
        f"{repo_path_for(world.project_id)}/info/refs", headers=_basic(world.owner_token)
    )
    assert response.status_code == 404
