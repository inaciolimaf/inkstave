"""Bounded tree reads + N+1 removal (spec 99).

In-memory unit tests (fake session) for the get_tree cap and its error, that the
files route no longer has a standalone entity-name lookup, and that the compile
source dict routes through the bounded get_tree. End-to-end query-count and route
status are covered by the integration suite.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from inkstave.services.tree_service import TreeTooLargeError, get_tree


class _ScalarsResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> list[Any]:
        return self._items


class FakeSession:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    async def execute(self, _stmt: Any) -> _ScalarsResult:
        return _ScalarsResult(self._items)


def _entities(n: int) -> list[Any]:
    return [SimpleNamespace(id=uuid4()) for _ in range(n)]


# --- #6.2 get_tree cap ----------------------------------------------------- #


async def test_get_tree_returns_rows_within_cap() -> None:
    items = _entities(2)
    assert await get_tree(FakeSession(items), uuid4(), max_nodes=2) == items


async def test_get_tree_returns_rows_below_cap() -> None:
    items = _entities(1)
    assert await get_tree(FakeSession(items), uuid4(), max_nodes=5) == items


async def test_get_tree_raises_when_over_cap() -> None:
    # Real DB fetches limit(cap+1); cap+1 rows materialised → over the limit.
    items = _entities(3)
    with pytest.raises(TreeTooLargeError):
        await get_tree(FakeSession(items), uuid4(), max_nodes=2)


def test_tree_too_large_error_shape_and_export() -> None:
    err = TreeTooLargeError()
    assert err.status_code == 422
    assert err.error_type == "tree_too_large"
    from inkstave.services import tree_service

    assert "TreeTooLargeError" in tree_service.__all__


# --- #6.1 no standalone entity-name lookup --------------------------------- #


def test_files_route_has_no_standalone_entity_name_lookup() -> None:
    from inkstave.api.routes import files as files_mod

    # The per-file TreeEntity SELECT helper is gone; _read uses file_row.entity.name.
    assert not hasattr(files_mod, "_entity_name")


# --- #6.3 compile sources route through the bounded get_tree --------------- #


async def test_compile_entities_by_id_uses_get_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave.compile import sources

    ents = _entities(3)

    async def fake_get_tree(_session: Any, _project_id: Any, **_kw: Any) -> list[Any]:
        return ents

    monkeypatch.setattr(sources, "get_tree", fake_get_tree)
    result = await sources._entities_by_id(object(), uuid4())
    assert result == {e.id: e for e in ents}


async def test_compile_entities_by_id_propagates_tree_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkstave.compile import sources

    async def fake_get_tree(_session: Any, _project_id: Any, **_kw: Any) -> list[Any]:
        raise TreeTooLargeError()

    monkeypatch.setattr(sources, "get_tree", fake_get_tree)
    with pytest.raises(TreeTooLargeError):
        await sources._entities_by_id(object(), uuid4())
