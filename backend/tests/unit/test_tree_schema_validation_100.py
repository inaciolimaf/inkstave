"""Fail-fast name-length constraints on tree request schemas (spec 100).

Pure Pydantic-level tests: empty / over-long names raise ValidationError at the
schema boundary; a name at exactly the limit is accepted; and the schema limit is
wired to the service constant so they cannot drift.
"""

from __future__ import annotations

import pytest
from annotated_types import MaxLen, MinLen
from pydantic import ValidationError

from inkstave.schemas.tree import CreateEntityIn, RenameEntityIn
from inkstave.services.safe_path import MAX_TREE_ENTITY_NAME_LENGTH


@pytest.mark.parametrize("bad", ["", "x" * (MAX_TREE_ENTITY_NAME_LENGTH + 1)])
def test_create_entity_rejects_empty_or_overlong_name(bad: str) -> None:
    with pytest.raises(ValidationError):
        CreateEntityIn(type="doc", name=bad)


@pytest.mark.parametrize("bad", ["", "x" * (MAX_TREE_ENTITY_NAME_LENGTH + 1)])
def test_rename_entity_rejects_empty_or_overlong_name(bad: str) -> None:
    with pytest.raises(ValidationError):
        RenameEntityIn(name=bad)


def test_valid_names_accepted() -> None:
    at_limit = "x" * MAX_TREE_ENTITY_NAME_LENGTH
    # Ordinary (non-padded) names — the schema measures the raw string, so the happy
    # path deliberately avoids surrounding whitespace.
    assert CreateEntityIn(type="doc", name=at_limit).name == at_limit
    assert CreateEntityIn(type="doc", name="main.tex").name == "main.tex"
    assert RenameEntityIn(name=at_limit).name == at_limit
    assert RenameEntityIn(name="main.tex").name == "main.tex"


@pytest.mark.parametrize("model", [CreateEntityIn, RenameEntityIn])
def test_schema_limit_matches_service_constant(model: type) -> None:
    meta = model.model_fields["name"].metadata
    assert any(isinstance(m, MaxLen) and m.max_length == MAX_TREE_ENTITY_NAME_LENGTH for m in meta)
    assert any(isinstance(m, MinLen) and m.min_length == 1 for m in meta)
    assert MAX_TREE_ENTITY_NAME_LENGTH == 255
