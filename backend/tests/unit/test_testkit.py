"""Unit tests for the e2e/test stubs (spec 54) — no DB, no network, no subprocess.

These are the cheap harness sanity checks: the compile mock emits a valid PDF +
log (and a LaTeX-error log for the sentinel), and the agent LLM stub scripts the
fixed search → read → propose_edit → reply sequence the agent journey relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.modules.agent.llm.base import LLMMessage
from inkstave.modules.agent.llm.stub import FINAL_REPLY, PROPOSED_TEXT, SEARCH_QUERY, StubAgentLLM
from inkstave.modules.compile.running.limits import CancelToken, ResourceLimits
from inkstave.modules.compile.running.stub import CANNED_PDF, MockTectonicRunner, build_minimal_pdf

_DOC_ID = "11111111-1111-1111-1111-111111111111"


def _limits() -> ResourceLimits:
    # The mock runner ignores limits; supply benign values to satisfy the type.
    return ResourceLimits(
        max_input_files=100,
        max_input_bytes=1_000_000,
        max_output_bytes=1_000_000,
        max_log_bytes=1_000_000,
        max_stdout_bytes=1_000_000,
        cpu_seconds=None,
        address_space_bytes=None,
    )


def test_build_minimal_pdf_is_structurally_valid() -> None:
    pdf = build_minimal_pdf("Hello")
    assert pdf.startswith(b"%PDF-1.4")
    assert b"startxref" in pdf
    assert pdf.rstrip().endswith(b"%%EOF")
    # Single page catalog/pages present.
    assert b"/Type /Catalog" in pdf and b"/Type /Page" in pdf
    assert CANNED_PDF.startswith(b"%PDF")


async def test_mock_runner_writes_pdf_and_log_on_success(tmp_path: Path) -> None:
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "main.tex").write_text("\\documentclass{article}\n", "utf-8")
    out = tmp_path / "output"

    outcome = await MockTectonicRunner().run(
        workdir=tmp_path,
        main_file="main.tex",
        output_dir=out,
        timeout_s=10,
        limits=_limits(),
        cancel=CancelToken(),
    )
    assert outcome.exit_code == 0 and not outcome.timed_out
    assert (out / "main.pdf").read_bytes().startswith(b"%PDF")
    assert "Output written" in (out / "main.log").read_text("utf-8")


async def test_mock_runner_emits_error_log_for_sentinel(tmp_path: Path) -> None:
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "main.tex").write_text("\\inkstaveforceerror\n", "utf-8")
    out = tmp_path / "output"

    outcome = await MockTectonicRunner().run(
        workdir=tmp_path,
        main_file="main.tex",
        output_dir=out,
        timeout_s=10,
        limits=_limits(),
        cancel=CancelToken(),
    )
    assert outcome.exit_code == 1
    assert not (out / "main.pdf").exists()
    assert "Undefined control sequence" in (out / "main.log").read_text("utf-8")


def _tool_msg(content: str, name: str = "t") -> LLMMessage:
    return LLMMessage(role="tool", name=name, content=content)


def _turn(*results: LLMMessage) -> list[LLMMessage]:
    """A turn's transcript: the user's message, then one model step and its tool result per entry."""
    messages = [LLMMessage(role="user", content="rewrite")]
    for result in results:
        messages += [LLMMessage(role="assistant", content=None), result]
    return messages


async def test_stub_llm_scripts_search_read_propose_reply() -> None:
    stub = StubAgentLLM()
    did = "11111111-1111-1111-1111-111111111111"
    search_result = _tool_msg(f'{{"ok":true,"data":{{"matches":[{{"doc_id":"{did}"}}]}}}}')
    read_text = '{"ok":true,"data":{"doc_id":"' + did + '","content":"stored text\\n"}}'
    read_result = _tool_msg(read_text, "read_file")

    r0 = await stub.complete([LLMMessage(role="user", content="rewrite")])
    assert r0.tool_calls[0].name == "search_project"
    assert r0.tool_calls[0].arguments["query"] == SEARCH_QUERY

    r1 = await stub.complete(_turn(search_result))
    assert r1.tool_calls[0].name == "read_file"
    assert r1.tool_calls[0].arguments["doc_id"] == did

    r2 = await stub.complete(_turn(search_result, read_result))
    assert r2.tool_calls[0].name == "propose_edit"
    assert r2.tool_calls[0].arguments == {
        "doc_id": did,
        "old_text": "stored text\n",
        "new_text": PROPOSED_TEXT,
    }

    staged = _tool_msg('{"staged":true}', "propose_edit")
    r3 = await stub.complete(_turn(search_result, read_result, staged))
    assert not r3.tool_calls and r3.content == FINAL_REPLY


async def test_stub_llm_answers_in_prose_when_no_doc_found() -> None:
    stub = StubAgentLLM()
    # A search result with no doc_id → the stub gives up rather than looping.
    r = await stub.complete(_turn(_tool_msg('{"ok":true,"data":{"matches":[]}}')))
    assert not r.tool_calls and r.finish_reason == "stop"


async def test_stub_llm_streams_final_reply() -> None:
    stub = StubAgentLLM()
    # Three steps done (one search carrying a doc_id) → the stub streams its final reply.
    history = _turn(
        _tool_msg(f'{{"data":{{"matches":[{{"doc_id":"{_DOC_ID}"}}]}}}}'),
        _tool_msg("{}", "read_file"),
        _tool_msg('{"staged":true}', "propose_edit"),
    )
    pieces = [c.delta async for c in stub.stream(history)]
    assert "".join(p for p in pieces if p) == FINAL_REPLY


async def test_stub_llm_waits_before_replying(monkeypatch: pytest.MonkeyPatch) -> None:
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr("inkstave.modules.agent.llm.stub.asyncio.sleep", fake_sleep)
    await StubAgentLLM(delay_s=0.4).complete([])
    assert pauses == [0.4]


async def test_stub_llm_plays_each_message_of_a_session_from_its_start() -> None:
    """A second message in the same session gets the search again, not the first turn's last step."""
    stub = StubAgentLLM()
    did = "11111111-1111-1111-1111-111111111111"
    first_turn = [
        LLMMessage(role="user", content="rewrite"),
        _tool_msg(f'{{"ok":true,"data":{{"matches":[{{"doc_id":"{did}"}}]}}}}'),
        _tool_msg('{"ok":true,"data":{"doc_id":"' + did + '","content":"stored text\\n"}}'),
        _tool_msg('{"staged":true}'),
        LLMMessage(role="assistant", content=FINAL_REPLY),
    ]
    r = await stub.complete([*first_turn, LLMMessage(role="user", content="rewrite it again")])
    assert r.tool_calls and r.tool_calls[0].name == "search_project"
