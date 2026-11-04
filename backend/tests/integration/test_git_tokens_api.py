"""Spec 121 §5.1 and §9: personal access tokens are created once, stored as hashes, listed and revoked."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User
from inkstave.modules.git.auth.tokens import MAX_ACTIVE_TOKENS
from inkstave.modules.git.models import GitAccessToken
from tests.factories import UserFactory
from tests.integration._git_support import GitWorld, git_enabled, repo_path_for, world

pytestmark = pytest.mark.integration

__all__ = ["git_enabled", "world"]  # the fixtures this module uses, re-exported for pytest

API = "/api/v1/git/tokens"


async def _jwt_headers(db_session: AsyncSession) -> dict[str, str]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def test_git_token_hash_only(
    async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    headers = await _jwt_headers(db_session)
    created = await async_client.post(API, json={"name": "  Laptop  "}, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    raw = body["token"]
    assert raw.startswith("ink_") and body["name"] == "Laptop"
    assert body["prefix"] == raw[:12]

    row = await db_session.scalar(select(GitAccessToken).where(GitAccessToken.prefix == raw[:12]))
    assert row is not None
    assert row.token_hash != raw and len(row.token_hash) == 64  # SHA-256 hex, never the token itself
    stored = " ".join(str(v) for v in vars(row).values())
    assert raw not in stored

    listed = await async_client.get(API, headers=headers)
    assert listed.status_code == 200
    assert "token" not in listed.json()["tokens"][0]  # shown once, never again


async def test_a_token_is_listed_then_revoked_and_stops_working(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    user = await db_session.get(User, world.owner_id)
    assert user is not None
    jwt, _ = build_token_service(get_settings()).create_access_token(user)
    headers = {"Authorization": f"Bearer {jwt}"}
    listed = (await async_client.get(API, headers=headers)).json()["tokens"]
    token_id = next(item["id"] for item in listed if item["name"] == "laptop")

    deleted = await async_client.delete(f"{API}/{token_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await async_client.get(API, headers=headers)).json()["tokens"] == [
        item for item in listed if item["id"] != token_id
    ]
    url = f"{repo_path_for(world.project_id)}/info/refs"
    response = await async_client.get(
        url,
        params={"service": "git-upload-pack"},
        headers={"Authorization": "Basic " + base64.b64encode(f"x:{world.owner_token}".encode()).decode()},
    )
    assert response.status_code == 401


async def test_a_token_belongs_to_its_owner_only(
    world: GitWorld, async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    other = await _jwt_headers(db_session)
    listed = (await async_client.get(API, headers=other)).json()["tokens"]
    assert listed == []
    row = await db_session.scalar(select(GitAccessToken).where(GitAccessToken.user_id == world.owner_id))
    assert row is not None
    response = await async_client.delete(f"{API}/{row.id}", headers=other)
    assert response.status_code == 404


async def test_a_user_holds_at_most_twenty_active_tokens(
    async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    headers = await _jwt_headers(db_session)
    for index in range(MAX_ACTIVE_TOKENS):
        response = await async_client.post(API, json={"name": f"t{index}"}, headers=headers)
        assert response.status_code == 201
    refused = await async_client.post(API, json={"name": "one too many"}, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["type"] == "token_limit"


async def test_an_expiry_in_the_past_is_refused(
    async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    headers = await _jwt_headers(db_session)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    response = await async_client.post(API, json={"name": "old", "expires_at": past}, headers=headers)
    assert response.status_code == 422


async def test_a_blank_name_is_refused(
    async_client: AsyncClient, db_session: AsyncSession, git_enabled: Any
) -> None:
    headers = await _jwt_headers(db_session)
    response = await async_client.post(API, json={"name": "   "}, headers=headers)
    assert response.status_code == 422


async def test_repeated_failed_attempts_are_rate_limited_per_ip(
    world: GitWorld, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_GIT_AUTH", "2/300")
    get_settings.cache_clear()
    url = f"{repo_path_for(world.project_id)}/info/refs"
    bad = {"Authorization": "Basic " + base64.b64encode(b"x:ink_not-a-token").decode()}
    statuses = [
        (await async_client.get(url, params={"service": "git-upload-pack"}, headers=bad)).status_code
        for _ in range(3)
    ]
    assert statuses == [401, 401, 429]
