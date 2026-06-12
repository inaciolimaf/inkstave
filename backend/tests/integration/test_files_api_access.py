"""Integration tests for the binary file API (spec 14): conflicts & permissions.

Covers parent/entity-type conflicts, duplicate-name handling, ownership
isolation between users, and the auth requirement. Shared helpers and fixtures
live in ``_files_api_support``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.storage.base import ObjectStore

from ._files_api_support import (
    _auth,
    _entity,
    _files,
    _project,
    _upload,
    client_store,
    object_store,
)

pytestmark = pytest.mark.integration

__all__ = ["client_store", "object_store"]


async def test_non_folder_parent(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    doc = await _entity(client, pid, headers, "doc", "main.tex")
    resp = await _upload(client, pid, headers, parent_id=doc)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "parent_not_a_folder"


async def test_duplicate_name(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    assert (await _upload(client, pid, headers, name="a.png")).status_code == 201
    dup = await _upload(client, pid, headers, name="a.png")
    assert dup.status_code == 409
    assert dup.json()["error"]["type"] == "name_conflict"


async def test_get_on_non_file_entity(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    folder = await _entity(client, pid, headers, "folder", "figs")
    resp = await client.get(f"{_files(pid)}/{folder}", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "not_a_file"


async def test_ownership_isolation(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers_a = await _auth(db_session)
    headers_b = await _auth(db_session)
    pid = await _project(client, headers_a)
    eid = (await _upload(client, pid, headers_a)).json()["entity_id"]
    for call in (
        client.get(f"{_files(pid)}/{eid}", headers=headers_b),
        client.get(f"{_files(pid)}/{eid}/content", headers=headers_b),
        client.delete(f"{_files(pid)}/{eid}", headers=headers_b),
    ):
        resp = await call
        assert resp.status_code == 404
        assert resp.json()["error"]["type"] == "project_not_found"


async def test_requires_auth(
    client_store: tuple[AsyncClient, ObjectStore], db_session: AsyncSession
) -> None:
    client, _ = client_store
    headers = await _auth(db_session)
    pid = await _project(client, headers)
    eid = (await _upload(client, pid, headers)).json()["entity_id"]
    assert (await client.get(f"{_files(pid)}/{eid}")).status_code == 401
