"""Unit tests for the e2e/test stubs (spec 54) — no DB, no network, no subprocess.

These are the cheap harness sanity checks: the compile mock emits a valid PDF +
log (and a LaTeX-error log for the sentinel), and the agent LLM stub scripts the
fixed search → read → propose_edit → reply sequence the agent journey relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.agent.llm.base import LLMMessage
from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.testkit.compile_stub import CANNED_PDF, MockTectonicRunner, build_minimal_pdf
from inkstave.testkit.llm_stub import FINAL_REPLY, PROPOSED_TEXT, SEARCH_QUERY, StubAgentLLM

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


def _tool_msg(content: str) -> LLMMessage:
    return LLMMessage(role="tool", name="t", content=content)


async def test_stub_llm_scripts_search_read_propose_reply() -> None:
    stub = StubAgentLLM()
    did = "11111111-1111-1111-1111-111111111111"

    r0 = await stub.complete([LLMMessage(role="user", content="rewrite")])
    assert r0.tool_calls[0].name == "search_project"
    assert r0.tool_calls[0].arguments["query"] == SEARCH_QUERY

    search_result = _tool_msg(f'{{"ok":true,"data":{{"matches":[{{"doc_id":"{did}"}}]}}}}')
    r1 = await stub.complete([search_result])
    assert r1.tool_calls[0].name == "read_file"
    assert r1.tool_calls[0].arguments["doc_id"] == did

    r2 = await stub.complete([search_result, _tool_msg('{"ok":true}')])
    assert r2.tool_calls[0].name == "propose_edit"
    assert r2.tool_calls[0].arguments == {"doc_id": did, "mode": "full", "new_text": PROPOSED_TEXT}

    r3 = await stub.complete([search_result, _tool_msg("{}"), _tool_msg('{"staged":true}')])
    assert not r3.tool_calls and r3.content == FINAL_REPLY


async def test_stub_llm_answers_in_prose_when_no_doc_found() -> None:
    stub = StubAgentLLM()
    # A search result with no doc_id → the stub gives up rather than looping.
    r = await stub.complete([_tool_msg('{"ok":true,"data":{"matches":[]}}')])
    assert not r.tool_calls and r.finish_reason == "stop"


@pytest.mark.parametrize("chunks", [1, 3])
async def test_stub_llm_streams_final_reply(chunks: int) -> None:
    stub = StubAgentLLM(stream_chunks=chunks)
    # Three tool results (one carrying a doc_id) → the stub streams its final reply.
    history = [
        _tool_msg(f'{{"data":{{"matches":[{{"doc_id":"{_DOC_ID}"}}]}}}}'),
        _tool_msg("{}"),
        _tool_msg('{"staged":true}'),
    ]
    pieces = [c.delta async for c in stub.stream(history)]
    assert "".join(p for p in pieces if p) == FINAL_REPLY
