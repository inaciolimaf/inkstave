"""Unit tests for project schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inkstave.schemas.project import ProjectCreate, ProjectRename


@pytest.mark.parametrize("schema", [ProjectCreate, ProjectRename])
class TestNameValidation:
    def test_trims_whitespace(self, schema: type[ProjectCreate]) -> None:
        assert schema(name="  My Paper  ").name == "My Paper"

    def test_rejects_blank(self, schema: type[ProjectCreate]) -> None:
        with pytest.raises(ValidationError):
            schema(name="   ")

    def test_rejects_empty(self, schema: type[ProjectCreate]) -> None:
        with pytest.raises(ValidationError):
            schema(name="")

    def test_rejects_oversized(self, schema: type[ProjectCreate]) -> None:
        with pytest.raises(ValidationError):
            schema(name="x" * 256)

    def test_accepts_max_length(self, schema: type[ProjectCreate]) -> None:
        assert schema(name="x" * 255).name == "x" * 255
