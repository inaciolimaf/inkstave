"""The API contract says what each field can hold, so the generated types need no narrowing."""

from __future__ import annotations

from functools import cache
from typing import Any

import pytest

from inkstave.app import create_app


@cache
def _openapi() -> dict[str, Any]:
    return create_app().openapi()


def _components() -> dict[str, Any]:
    return _openapi()["components"]["schemas"]


def _enum(schema: dict[str, Any]) -> set[str]:
    if "$ref" in schema:
        return _enum(_components()[schema["$ref"].rsplit("/", 1)[-1]])
    return set(schema["enum"])


@pytest.mark.parametrize(
    ("model", "field", "values"),
    [
        ("AgentMessageOut", "role", {"system", "user", "assistant", "tool"}),
        (
            "CompileStatusResponse",
            "status",
            {"queued", "running", "success", "failure", "timeout", "cancelled", "error"},
        ),
        ("MemberRead", "role", {"owner", "editor", "viewer"}),
        ("InviteRead", "role", {"editor", "viewer"}),
        ("InvitePreview", "role", {"editor", "viewer"}),
        ("AcceptResponse", "role", {"owner", "editor", "viewer"}),
        ("PermissionsRead", "role", {"owner", "editor", "viewer"}),
        ("DiffSegment", "type", {"context", "added", "removed"}),
    ],
)
def test_closed_fields_publish_their_values(model: str, field: str, values: set[str]) -> None:
    assert _enum(_components()[model]["properties"][field]) == values


def _array_item(schema: dict[str, Any]) -> str:
    array = next(option for option in schema["anyOf"] if option.get("type") == "array")
    return array["items"]["$ref"].rsplit("/", 1)[-1]


def test_tool_calls_and_hunks_have_a_shape() -> None:
    components = _components()
    assert _array_item(components["AgentMessageOut"]["properties"]["tool_calls"]) == "ToolCall"
    assert _array_item(components["ProposedDiffSummary"]["properties"]["hunks"]) == "Hunk"
    assert components["HunkLine"]["properties"]["op"]["enum"] == [" ", "-", "+"]


def test_history_diff_documents_its_body_for_both_success_codes() -> None:
    path = "/api/v1/projects/{project_id}/docs/{doc_id}/history/diff"
    responses = _openapi()["paths"][path]["get"]["responses"]
    for code in ("200", "413"):
        body = responses[code]["content"]["application/json"]["schema"]
        assert body == {"$ref": "#/components/schemas/DiffResponse"}
    assert set(_components()["DiffResponse"]["properties"]) == {"from", "to", "binary", "too_large", "hunks"}
