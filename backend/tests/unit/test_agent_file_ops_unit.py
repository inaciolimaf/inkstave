"""Pure parts of the agent's file operations and images."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inkstave.modules.agent.file_ops.paths import (
    ancestors_of,
    name_of,
    normalize_path,
    parent_of,
    subtree_paths,
)
from inkstave.modules.agent.llm.anthropic_client import _to_anthropic_messages
from inkstave.modules.agent.llm.base import LLMImage, LLMMessage
from inkstave.modules.agent.llm.openrouter import OpenRouterLLMClient
from inkstave.modules.agent.tools.base import ToolResult
from inkstave.modules.agent.tools.files.propose import ProposeCreateArgs
from inkstave.modules.agent.tools.files.view_image import sniff_image

IMAGE = LLMImage(media_type="image/png", data="QUJD")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("a/b.tex", "a/b.tex"), ("/a/b.tex", "a/b.tex"), ("./a/", "a"), (" a ", "a"), ("/", ""), (".", ".")],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


def test_path_parts() -> None:
    assert parent_of("a/b/c.tex") == "a/b" and parent_of("c.tex") == ""
    assert name_of("a/b/c.tex") == "c.tex"
    assert ancestors_of("a/b/c.tex") == ["a", "a/b"]


def test_subtree_paths_does_not_take_a_name_that_only_starts_alike() -> None:
    assert subtree_paths(["a", "a/x", "ab", "b"], "a") == ["a", "a/x"]


def test_a_folder_takes_no_content() -> None:
    with pytest.raises(ValidationError):
        ProposeCreateArgs(path="a", type="folder", content="x")


@pytest.mark.parametrize(
    ("head", "media_type"),
    [
        (b"\x89PNG\r\n\x1a\n....", "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"GIF89a", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8", "image/webp"),
        (b"%PDF-1.7", None),
        (b"<svg xmlns=", None),
    ],
)
def test_sniff_image(head: bytes, media_type: str | None) -> None:
    assert sniff_image(head) == media_type


def test_images_stay_out_of_what_gets_stored() -> None:
    result = ToolResult(ok=True, data={"path": "a.png"}, images=[IMAGE])
    assert IMAGE.data not in result.model_dump_json()
    message = LLMMessage(role="tool", content="{}", images=[IMAGE])
    assert "images" not in message.model_dump()


def test_anthropic_puts_the_image_inside_the_tool_result() -> None:
    message = LLMMessage(role="tool", tool_call_id="c1", content="{}", images=[IMAGE])
    _, turns = _to_anthropic_messages([message])
    content = turns[0]["content"][0]["content"]
    assert content[0] == {"type": "text", "text": "{}"}
    assert content[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}


def test_openrouter_sends_the_image_after_the_last_tool_result() -> None:
    messages = [
        LLMMessage(role="tool", tool_call_id="c1", content="{}", images=[IMAGE]),
        LLMMessage(role="tool", tool_call_id="c2", content="{}"),
        LLMMessage(role="assistant", content="seen"),
    ]
    out = OpenRouterLLMClient._to_openai_messages(messages)
    assert [m["role"] for m in out] == ["tool", "tool", "user", "assistant"]
    assert out[1]["content"] == "{}"
    assert out[2]["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"
