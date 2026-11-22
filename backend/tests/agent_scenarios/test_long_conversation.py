"""Scenarios: a conversation that goes on. Several messages, a second one while a run is active,
reloads of the session during and after a run, and proposals that must land on their own turn.

The HTTP routes are real. The enqueuer is a recorder: the test runs each queued job itself, through
``run_agent_turn``, with a scripted model.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.agent.deps import get_agent_enqueuer
from inkstave.modules.agent.models import AgentSession
from inkstave.modules.agent.scripted.steps import Call, Calls, Do, Reply, ScriptedLLM
from inkstave.modules.auth.credentials.tokens import build_token_service
from tests.agent_scenarios.support import make_project, play_turn

pytestmark = pytest.mark.integration

API = "/api/v1/projects"


class _Recorder:
    """Stands in for the ARQ queue: remembers each enqueued turn, runs nothing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def enqueue(self, *, session_id: UUID, run_id: UUID, user_message: str) -> str | None:
        self.calls.append({"session_id": session_id, "run_id": run_id, "message": user_message})
        return "job"


@pytest.fixture
async def routed(app: Any, db_session: AsyncSession, async_client: AsyncClient) -> SimpleNamespace:
    project = await make_project(db_session)
    project_id = project.proj.id
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(project.owner)
    recorder = _Recorder()
    app.dependency_overrides[get_agent_enqueuer] = lambda: recorder
    headers = {"Authorization": f"Bearer {token}"}
    created = await async_client.post(f"{API}/{project.proj.id}/agent/sessions", json={}, headers=headers)
    assert created.status_code == 201
    return SimpleNamespace(
        project=project,
        headers=headers,
        recorder=recorder,
        client=async_client,
        session_id=UUID(created.json()["id"]),
        project_id=project_id,
    )


def _base(routed: SimpleNamespace) -> str:
    return f"{API}/{routed.project_id}/agent/sessions/{routed.session_id}"


async def _send(routed: SimpleNamespace, text: str) -> tuple[int, dict[str, Any]]:
    response = await routed.client.post(
        f"{_base(routed)}/messages", json={"content": text}, headers=routed.headers
    )
    return response.status_code, response.json()


async def _detail(routed: SimpleNamespace) -> dict[str, Any]:
    response = await routed.client.get(_base(routed), headers=routed.headers)
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


async def _run_queued(routed: SimpleNamespace, db: AsyncSession, redis: Any, llm: Any) -> Any:
    """Run the most recently enqueued turn through the real job."""
    queued = routed.recorder.calls[-1]
    session = await db.get(AgentSession, routed.session_id)
    assert session is not None
    return await play_turn(db, redis, session, llm, queued["message"], run_id=queued["run_id"])


async def test_three_messages_in_a_row_each_run_completes_and_the_history_grows(
    routed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    replies = ["one", "two", "three"]
    seen: list[ScriptedLLM] = []
    for index, reply in enumerate(replies):
        status, _ = await _send(routed, f"message {index}")
        assert status == 202
        llm = ScriptedLLM([Reply(reply)])
        seen.append(llm)
        sink = await _run_queued(routed, db_session, redis, llm)
        # Each run numbers its own events from 0: the panel must not drop the second run's first event.
        assert [e["seq"] for e in sink.events] == list(range(len(sink.events)))
        assert sink.events[-1]["type"] == "done"

    shown = [m.content for m in seen[2].calls[0] if m.role in ("user", "assistant")]
    assert shown == ["message 0", "one", "message 1", "two", "message 2"]
    detail = await _detail(routed)
    assert [m["seq"] for m in detail["messages"]] == list(range(6))
    assert [m["content"] for m in detail["messages"]][-1] == "three"


async def test_a_message_while_a_run_is_active_is_refused_and_one_after_it_is_accepted(
    routed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    assert (await _send(routed, "first"))[0] == 202
    status, body = await _send(routed, "second, too soon")
    assert status == 409
    assert body["error"]["type"] == "run_active"
    assert len(routed.recorder.calls) == 1  # the refused message enqueued nothing

    await _run_queued(routed, db_session, redis, ScriptedLLM([Reply("done")]))
    assert (await _send(routed, "third"))[0] == 202
    assert len(routed.recorder.calls) == 2


async def test_the_session_reloaded_during_a_run_shows_it_running_and_not_yet_the_turn(
    routed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    _, started = await _send(routed, "rewrite the intro")
    before = await _detail(routed)
    assert before["session"]["run_state"] == "queued"
    assert before["session"]["active_run_id"] == str(started["run_id"])

    during: list[dict[str, Any]] = []

    async def reload_mid_run() -> None:
        during.append(await _detail(routed))

    llm = ScriptedLLM([Do(reload_mid_run, then=Reply("Here is the intro."))])
    await _run_queued(routed, db_session, redis, llm)

    assert during[0]["session"]["run_state"] == "running"

    after = await _detail(routed)
    assert after["session"]["run_state"] == "done"
    assert [m["role"] for m in after["messages"]] == ["user", "assistant"]
    assert after["messages"][-1]["content"] == "Here is the intro."


def _two_edit_turns(main: UUID, notes: UUID) -> list[tuple[str, list[Any]]]:
    """Two messages, each reading one file and proposing an edit to it."""
    return [
        (
            "tweak the intro",
            [
                Calls((Call("read_file", {"doc_id": str(main)}),)),
                Calls(
                    (Call("propose_edit", {"doc_id": str(main), "old_text": "motivates", "new_text": "M"}),)
                ),
                Reply("First change is ready."),
            ],
        ),
        (
            "now the notes",
            [
                Calls((Call("read_file", {"doc_id": str(notes)}),)),
                Calls(
                    (
                        Call(
                            "propose_edit",
                            {"doc_id": str(notes), "old_text": "cite the survey", "new_text": "cite it"},
                        ),
                    )
                ),
                Reply("Second change is ready."),
            ],
        ),
    ]


async def test_each_proposal_is_attached_to_the_message_of_its_own_turn(
    routed: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    turns = _two_edit_turns(routed.project.main_id, routed.project.notes_id)
    for message, script in turns:
        await _send(routed, message)
        await _run_queued(routed, db_session, redis, ScriptedLLM(script))

    detail = await _detail(routed)
    replies = {m["content"]: m["id"] for m in detail["messages"] if m["role"] == "assistant"}
    attached = {d["path"]: d["message_id"] for d in detail["diffs"]}
    assert attached == {
        "main.tex": replies["First change is ready."],
        "notes.tex": replies["Second change is ready."],
    }
