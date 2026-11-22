"""Scenarios: the provider misbehaves: an empty reply, a rate limit, a reply cut off, a cancel.

Two kinds of failure are covered. Scripted steps stand for what the graph receives. The real
Anthropic client runs over an httpx mock transport, so the SDK's own retries and error mapping are
the ones in use. No network is opened.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx  # the SDK's own HTTP package (anthropic 2.x), not the app's httpx
import pytest
from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.modules.agent.llm.anthropic_client import AnthropicLLMClient
from inkstave.modules.agent.llm.base import LLMError
from inkstave.modules.agent.runs.events import request_cancel
from inkstave.modules.agent.scripted.steps import Call, Calls, Do, Reply, ScriptedLLM, Stream
from tests.agent_scenarios.support import (
    MAIN_TEX,
    diffs_of,
    doc_text,
    final_text,
    make_project,
    new_session,
    play_turn,
    queue_run,
    transcript,
    unanswered_tool_calls,
)

pytestmark = pytest.mark.integration

CAPPED_MARK = "stopped before finishing"
NARRATION = "Let me read the file."
SSE_HEADERS = {"content-type": "text/event-stream"}


@pytest.fixture
async def project(db_session: AsyncSession) -> SimpleNamespace:
    return await make_project(db_session)


# --- the real client over a mock transport -------------------------------------------------------


def _event(name: str, data: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


def _text_head(*parts: str) -> bytes:
    """The start of a text message: its header and whatever text has arrived so far."""
    body = [
        _event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-haiku-5-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 3, "output_tokens": 0},
                },
            },
        ),
        _event(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
    ]
    body += [
        _event(
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": p}},
        )
        for p in parts
    ]
    return b"".join(body)


def _text_reply(text: str) -> bytes:
    tail = [
        _event("content_block_stop", {"type": "content_block_stop", "index": 0}),
        _event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 2},
            },
        ),
        _event("message_stop", {"type": "message_stop"}),
    ]
    return _text_head(text) + b"".join(tail)


class _BrokenBody(httpx.AsyncByteStream):
    """A reply whose connection fails after its first bytes."""

    def __init__(self, head: bytes, error: Exception) -> None:
        self._head = head
        self._error = error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._head
        raise self._error


def _real_client(handler: Callable[[httpx.Request], Any], *, max_retries: int) -> AnthropicLLMClient:
    """The real client, its SDK pointed at a mock transport instead of the network."""
    client = AnthropicLLMClient(AgentSettings(anthropic_api_key="test-key"))
    transport = httpx.MockTransport(handler)
    client._client = AsyncAnthropic(
        api_key="test-key",
        max_retries=max_retries,
        http_client=httpx.AsyncClient(transport=transport),
    )
    return client


def _rate_limited() -> httpx.Response:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    return httpx.Response(429, headers={"retry-after-ms": "1"}, json=body)


async def test_a_rate_limit_is_retried_by_the_sdk_and_the_run_completes(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    attempts: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return _rate_limited()
        return httpx.Response(200, headers=SSE_HEADERS, content=_text_reply("Hello there."))

    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, _real_client(handler, max_retries=2), "hi")

    assert len(attempts) == 2
    assert final_text(sink) == "Hello there."
    assert sink.events[-1]["type"] == "done"


async def test_a_rate_limit_that_outlasts_the_retries_ends_the_run_and_the_next_message_works(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return _rate_limited()

    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, _real_client(handler, max_retries=0), "hi")

    assert sink.events[-1]["type"] == "error" and sink.events[-1]["code"] == "internal"
    assert session.run_state == "error" and session.active_run_id is None

    later = ScriptedLLM([Reply("Back again.")])
    sink2 = await play_turn(db_session, redis, session, later, "hi again")
    assert final_text(sink2) == "Back again." and sink2.events[-1]["type"] == "done"
    assert session.run_state == "done"


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("timed out"), httpx.ReadError("connection reset")])
async def test_a_real_client_failure_after_some_text_ends_the_run_as_an_error(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any, failure: Exception
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        body = _BrokenBody(_text_head("I will rewrite ", "the intro"), failure)
        return httpx.Response(200, headers=SSE_HEADERS, stream=body)

    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, _real_client(handler, max_retries=0), "rewrite")

    await _assert_failed_mid_reply(db_session, project, session, sink)


# --- scripted failures ----------------------------------------------------------------------------


@pytest.mark.parametrize("failure", [RuntimeError("boom"), LLMError("LLM stream failed: reset")])
async def test_a_scripted_failure_after_some_tokens_ends_the_run_as_an_error(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any, failure: Exception
) -> None:
    llm = ScriptedLLM([Stream(("I will rewrite ", "the intro"), failure)])
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "rewrite")

    await _assert_failed_mid_reply(db_session, project, session, sink)


async def _assert_failed_mid_reply(
    db: AsyncSession, project: SimpleNamespace, session: Any, sink: Any
) -> None:
    """The panel saw the partial text and then an error; the partial reply is not kept anywhere."""
    assert "I will rewrite the intro" in final_text(sink)
    assert sink.events[-1]["type"] == "error" and sink.events[-1]["code"] == "internal"
    assert session.run_state == "error" and session.active_run_id is None
    stored = await transcript(db, session)
    assert all("I will rewrite" not in (m.content or "") for m in stored)
    assert await diffs_of(db, session) == []
    assert await doc_text(db, project, project.main_id) == MAIN_TEX


@pytest.mark.xfail(reason="known bug: an empty model reply ends as a capped answer (fixed next)", strict=True)
async def test_an_empty_reply_is_reported_as_a_failure_not_as_a_capped_answer(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    doc = project.main_id
    llm = ScriptedLLM([Calls((Call("read_file", {"doc_id": str(doc)}),), text=NARRATION), Reply(None)])
    session = await new_session(db_session, project)
    sink = await play_turn(db_session, redis, session, llm, "read it")

    assert CAPPED_MARK not in final_text(sink)
    assert sink.events[-1]["type"] == "error"
    closing = [m for m in await transcript(db_session, session) if m.role == "assistant"][-1]
    assert closing.content and closing.content != NARRATION


@pytest.mark.xfail(reason="known bug: a cancelled tool call stays in the history (fixed next)", strict=True)
async def test_a_cancel_during_a_tool_call_ends_cancelled_and_the_next_message_has_a_valid_history(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    session = await new_session(db_session, project)
    run_id = await queue_run(db_session, session)

    async def user_presses_stop() -> None:
        await request_cancel(redis, run_id, 900)

    llm = ScriptedLLM(
        [Do(user_presses_stop, then=Calls((Call("read_file", {"doc_id": str(project.main_id)}),)))]
    )
    sink = await play_turn(db_session, redis, session, llm, "read it", run_id=run_id)

    assert sink.events[-1]["type"] == "error" and sink.events[-1]["code"] == "cancelled"
    assert await diffs_of(db_session, session) == []

    later = ScriptedLLM([Reply("Sure.")])
    await play_turn(db_session, redis, session, later, "and now?")
    assert unanswered_tool_calls(later.calls[0]) == []


async def test_a_cancel_during_a_text_answer_lets_that_answer_finish(
    project: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    """Cancel is cooperative (docs/system/agent.md): a model call in flight runs to its end."""
    session = await new_session(db_session, project)
    run_id = await queue_run(db_session, session)

    async def user_presses_stop() -> None:
        await request_cancel(redis, run_id, 900)

    llm = ScriptedLLM([Do(user_presses_stop, then=Reply("The answer."))])
    sink = await play_turn(db_session, redis, session, llm, "question", run_id=run_id)

    assert final_text(sink) == "The answer."
    assert sink.events[-1]["type"] == "done"
