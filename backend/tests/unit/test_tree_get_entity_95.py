"""The single shared TreeEntity-fetch helper (spec 95 §TE-1).

Pure unit tests with a fake async session — no DB. They pin the parity the four
former call sites rely on: missing → EntityNotFoundError; wrong type → the
caller's factory error (or EntityNotFoundError when none is supplied, the collab
join-check behaviour).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.services.document_service import NotADocumentError
from inkstave.services.file_service import NotAFileError
from inkstave.services.tree_service import EntityNotFoundError, get_entity


class _Result:
    def __init__(self, entity: Any) -> None:
        self._entity = entity

    def scalar_one_or_none(self) -> Any:
        return self._entity


class FakeSession:
    def __init__(self, entity: Any = None) -> None:
        self._entity = entity

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self._entity)


def _entity(entity_type: TreeEntityType) -> Any:
    return SimpleNamespace(id=uuid4(), type=entity_type)


async def test_found_returns_entity() -> None:
    ent = _entity(TreeEntityType.folder)
    assert await get_entity(FakeSession(ent), uuid4(), uuid4()) is ent


async def test_missing_raises_entity_not_found() -> None:
    with pytest.raises(EntityNotFoundError) as exc:
        await get_entity(FakeSession(None), uuid4(), uuid4())
    assert str(exc.value) == "Tree entity not found."


async def test_doc_type_match_returns_entity() -> None:
    ent = _entity(TreeEntityType.doc)
    result = await get_entity(
        FakeSession(ent),
        uuid4(),
        uuid4(),
        expected_type=TreeEntityType.doc,
        wrong_type_error=NotADocumentError,
    )
    assert result is ent


async def test_wrong_type_doc_raises_not_a_document() -> None:
    ent = _entity(TreeEntityType.file)
    with pytest.raises(NotADocumentError):
        await get_entity(
            FakeSession(ent),
            uuid4(),
            uuid4(),
            expected_type=TreeEntityType.doc,
            wrong_type_error=NotADocumentError,
        )


async def test_wrong_type_file_raises_not_a_file() -> None:
    ent = _entity(TreeEntityType.doc)
    with pytest.raises(NotAFileError):
        await get_entity(
            FakeSession(ent),
            uuid4(),
            uuid4(),
            expected_type=TreeEntityType.file,
            wrong_type_error=NotAFileError,
        )


async def test_wrong_type_without_factory_falls_back_to_not_found() -> None:
    # Collab join check passes no factory: a non-doc id maps to EntityNotFoundError
    # (which the collab path translates to CLOSE_NOT_FOUND).
    ent = _entity(TreeEntityType.file)
    with pytest.raises(EntityNotFoundError):
        await get_entity(FakeSession(ent), uuid4(), uuid4(), expected_type=TreeEntityType.doc)
