"""The e2e stub LLM reads tool results the way the graph hands them over (spec 54 / spec 49)."""

from __future__ import annotations

import json

from inkstave.modules.agent.llm.base import LLMMessage
from inkstave.modules.agent.llm.stub import StubAgentLLM
from inkstave.modules.agent.safety.injection import wrap_untrusted

DOC_ID = "13ad2ddf-e01f-479e-bcc9-20987a9ea320"
TEXT = "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}\nOriginal.\n\\end{document}\n"


def _framed(name: str, data: dict[str, object]) -> LLMMessage:
    # The graph frames every tool result before the provider sees it (nodes.py: frame_untrusted).
    body = json.dumps({"ok": True, "data": data, "error": None})
    return LLMMessage(role="tool", name=name, content=wrap_untrusted("tool_result", body))


async def test_stub_proposes_the_read_text_as_old_text_through_the_untrusted_frame() -> None:
    search = _framed(
        "search_project", {"matches": [{"doc_id": DOC_ID, "path": "main.tex", "line": 2}], "truncated": False}
    )
    read = _framed("read_file", {"doc_id": DOC_ID, "path": "main.tex", "content": TEXT, "truncated": False})
    # The stub picks its step from the assistant calls made since the user's message, as in a real turn.
    messages = [
        LLMMessage(role="user", content="Rewrite the introduction."),
        LLMMessage(role="assistant", content=""),
        search,
        LLMMessage(role="assistant", content=""),
        read,
    ]

    response = await StubAgentLLM(delay_s=0).complete(messages)

    assert response.tool_calls is not None
    call = response.tool_calls[0]
    assert call.name == "propose_edit"
    assert call.arguments["doc_id"] == DOC_ID
    # An empty old_text is refused by propose_edit (exact-match rule): the stub must echo the read text.
    assert call.arguments["old_text"] == TEXT
