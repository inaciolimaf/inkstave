"""Named scripts for the e2e stub (``LLM_STUB_SCENARIO``, test only).

Each scenario is search → read → propose on the document that contains :data:`SEARCH_QUERY`, with one
mistake a real model makes, or none for ``happy``. The mistake reaches the model as a tool error or a
provider failure, and the scenario then recovers or ends the run, as its name says. The backend scenario
tests (``backend/tests/agent_scenarios``) run the same scripts through the real graph.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from inkstave.modules.agent.llm.base import LLMError, LLMMessage
from inkstave.modules.agent.scripted.steps import Call, Calls, Compute, Reply, Step, Stream

#: The keyword the stub searches for; the e2e seeds a doc containing it.
SEARCH_QUERY = "Introduction"

#: The replacement body the stub proposes for the text it read; differs from the seeded file
#: so there is always a reviewable hunk.
PROPOSED_TEXT = (
    "\\documentclass{article}\n"
    "\\begin{document}\n"
    "\\section{Introduction}\n"
    "This paragraph was rewritten by the Inkstave AI agent.\n"
    "\\end{document}\n"
)

#: The fixed assistant reply once the edit is staged.
FINAL_REPLY = (
    "I searched the project, read the document, and prepared a rewrite of the "
    "introduction. Review the proposed diff and apply it when you're ready."
)

NO_DOCUMENT_REPLY = "I couldn't find a document to edit in this project."

#: Every name ``LLM_STUB_SCENARIO`` accepts.
SCENARIO_NAMES: tuple[str, ...] = (
    "happy",
    "propose_without_read",
    "old_text_not_found",
    "malformed_arguments",
    "unknown_tool",
    "empty_reply",
    "provider_error",
    "stream_cut",
)

_DOC_ID_RE = re.compile(r'"doc_id"\s*:\s*"([0-9a-fA-F-]{36})"')
_BAD_OLD_TEXT = "\\section{Conclusions}"
_SECTION_OLD_TEXT = "\\section{Introduction}"


def first_doc_id(messages: list[LLMMessage]) -> str | None:
    """The first document id a tool result mentioned (the search hit the stub edits)."""
    for message in messages:
        if message.role == "tool":
            match = _DOC_ID_RE.search(message.content or "")
            if match:
                return match.group(1)
    return None


def read_text(messages: list[LLMMessage]) -> str:
    """The text of the last ``read_file`` result, as the model read it; empty when there is none."""
    for message in reversed(messages):
        if message.role == "tool" and message.name == "read_file":
            content = _data_of(message.content).get("content")
            return content if isinstance(content, str) else ""
    return ""


def _data_of(tool_json: str | None) -> dict[str, Any]:
    """The ``data`` object of a tool result. The model sees results framed as untrusted content
    (spec 49), so the JSON is found inside the frame instead of being parsed from its first byte."""
    text = tool_json or ""
    start = text.find("{")
    if start < 0:
        return {}
    try:
        payload, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError:
        return {}
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def _on_document(make: Callable[[str], Step]) -> Step:
    """A step for the document the search found; a plain answer when the search found none."""

    def step_for(messages: list[LLMMessage]) -> Step:
        doc_id = first_doc_id(messages)
        if doc_id is None:
            return Reply(NO_DOCUMENT_REPLY)
        return make(doc_id)

    return Compute(step_for)


def _search() -> Step:
    return Calls((Call("search_project", {"query": SEARCH_QUERY}),))


def _read() -> Step:
    return _on_document(lambda doc: Calls((Call("read_file", {"doc_id": doc}),)))


def _propose(old_text: str) -> Step:
    return _on_document(
        lambda doc: Calls(
            (Call("propose_edit", {"doc_id": doc, "old_text": old_text, "new_text": PROPOSED_TEXT}),)
        )
    )


def _propose_read_text() -> Step:
    """The correct edit: the whole text the last read returned, replaced by the proposal."""

    def step_for(messages: list[LLMMessage]) -> Step:
        doc_id = first_doc_id(messages) or ""
        arguments = {"doc_id": doc_id, "old_text": read_text(messages), "new_text": PROPOSED_TEXT}
        return Calls((Call("propose_edit", arguments),))

    return Compute(step_for)


def _final() -> Step:
    return Reply(FINAL_REPLY)


def _happy_edit() -> tuple[Step, ...]:
    return (_read(), _propose_read_text(), _final())


_SCENARIOS: dict[str, tuple[Step, ...]] = {
    "happy": (_search(), *_happy_edit()),
    "propose_without_read": (_search(), _propose(_SECTION_OLD_TEXT), *_happy_edit()),
    "old_text_not_found": (_search(), _read(), _propose(_BAD_OLD_TEXT), _propose_read_text(), _final()),
    "malformed_arguments": (
        _search(),
        Calls((Call("read_file", raw='{"doc_id": "'),)),
        _read(),
        _propose_read_text(),
        _final(),
    ),
    "unknown_tool": (
        _search(),
        Calls((Call("rewrite_document", {"instructions": "shorter"}),)),
        *_happy_edit(),
    ),
    "empty_reply": (_search(), Reply(None)),
    "provider_error": (_search(), _read(), Stream((), LLMError("LLM request failed: service unavailable"))),
    "stream_cut": (
        _search(),
        _read(),
        Stream(("I will rewrite the ", "introduction now"), ConnectionError("connection reset")),
    ),
}


def scenario_steps(name: str) -> tuple[Step, ...]:
    """The steps of one named scenario; an unknown name is a configuration error."""
    try:
        return _SCENARIOS[name]
    except KeyError:
        raise ValueError(
            f"unknown LLM_STUB_SCENARIO {name!r}; expected one of {', '.join(SCENARIO_NAMES)}"
        ) from None


__all__ = [
    "FINAL_REPLY",
    "NO_DOCUMENT_REPLY",
    "PROPOSED_TEXT",
    "SCENARIO_NAMES",
    "SEARCH_QUERY",
    "scenario_steps",
]
