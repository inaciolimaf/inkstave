"""Paging of comment threads: oldest first, a cursor per page, a default and a cap on the page size."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.test_comments_api import _comments, _room, _start

pytestmark = pytest.mark.integration


async def _threads(client: AsyncClient, pid: str, headers: dict[str, str], count: int, doc: str) -> list[str]:
    return [str((await _start(client, pid, headers, doc, f"thread {n}"))["id"]) for n in range(count)]


async def _walk(client: AsyncClient, url: str, headers: dict[str, str]) -> tuple[list[str], int]:
    """Follow ``next_cursor`` from ``url`` to the end; return the ids seen and the number of pages."""
    seen: list[str] = []
    pages = 0
    cursor: str | None = None
    while True:
        query = url if cursor is None else f"{url}&after={cursor}"
        response = await client.get(query, headers=headers)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        pages += 1
        seen.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        assert body["has_more"] is (cursor is not None)
        if cursor is None:
            return seen, pages


async def test_pages_follow_the_cursor_oldest_first_without_gaps(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, doc, headers = room["pid"], room["doc"], room["owner"][1]
    created = await _threads(async_client, pid, headers, 5, doc)

    seen, pages = await _walk(async_client, f"{_comments(pid)}?status=all&limit=2", headers)

    assert seen == created  # creation order, every thread once
    assert pages == 3


async def test_the_default_page_is_fifty_threads(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, doc, headers = room["pid"], room["doc"], room["owner"][1]
    await _threads(async_client, pid, headers, 51, doc)

    first = await async_client.get(_comments(pid), headers=headers)

    assert first.status_code == 200
    assert len(first.json()["items"]) == 50
    assert first.json()["has_more"] is True


async def test_page_size_is_capped_and_must_be_positive(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    room = await _room(async_client, db_session)
    pid, headers = room["pid"], room["owner"][1]

    for limit in (0, 101):
        response = await async_client.get(f"{_comments(pid)}?limit={limit}", headers=headers)
        assert response.status_code == 422, limit


async def test_a_garbled_cursor_is_400(async_client: AsyncClient, db_session: AsyncSession) -> None:
    room = await _room(async_client, db_session)
    pid, headers = room["pid"], room["owner"][1]

    response = await async_client.get(f"{_comments(pid)}?after=not-a-cursor!!", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_cursor"
