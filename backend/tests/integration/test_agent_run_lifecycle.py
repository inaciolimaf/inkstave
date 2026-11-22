"""Integration: a run always settles, and a dead run never blocks the session (spec 44/49)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.agent import AgentSettings
from inkstave.core.config.settings import get_settings
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.llm.fake import FakeLLM
from inkstave.modules.agent.models import AgentRunState, AgentSession
from inkstave.modules.agent.runs.events import InMemoryEventSink, last_event_key
from inkstave.modules.agent.runs.jobs import run_agent_turn
from inkstave.modules.agent.safety import acquire_run
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.catalog.service import create_project
from tests.factories import UserFactory

from ._agent_api_support import API, _FakeEnqueuer, _SessionCtx, enqueuer

__all__ = ["enqueuer"]

pytestmark = pytest.mark.integration

_NOW = 1000.0


@pytest.fixture
async def run(db_session: AsyncSession) -> SimpleNamespace:
    """A queued session whose run has no progress recorded yet (the worker has not started it)."""
    owner = await UserFactory.create(db_session)
    project = await create_project(db_session, owner.id, "Paper")
    session = await agent_repo.create_session(
        db_session, project_id=project.id, user_id=owner.id, model="fake/model"
    )
    session.active_run_id = uuid4()
    session.run_state = AgentRunState.queued.value
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(owner)
    return SimpleNamespace(
        owner=owner,
        project=project,
        session=session,
        run_id=session.active_run_id,
        headers={"Authorization": f"Bearer {token}"},
    )


class _DownRedis:
    """Every Redis command fails with a real connection error (Redis unreachable)."""

    def __getattr__(self, _name: str) -> Any:
        async def _down(*_args: object, **_kwargs: object) -> None:
            raise RedisConnectionError("redis down")

        return _down


def _ctx(db: AsyncSession, redis: Any, settings: AgentSettings, **extra: Any) -> dict[str, Any]:
    return {
        "settings": settings,
        "session_factory": lambda: _SessionCtx(db),
        "redis": redis,
        "clock": lambda: _NOW,
        **extra,
    }


async def _state(db: AsyncSession, run: SimpleNamespace) -> AgentSession:
    row = await db.get(AgentSession, run.session.id)
    assert row is not None
    await db.refresh(row)
    return row


async def _assert_released(db: AsyncSession, run: SimpleNamespace) -> None:
    row = await _state(db, run)
    assert row.run_state == AgentRunState.error.value
    assert row.active_run_id is None


async def _run_turn_without_key(db: AsyncSession, run: SimpleNamespace, redis: Any) -> None:
    """A turn with no injected LLM, so the real client is built, and no API key configured."""
    await run_agent_turn(
        _ctx(db, redis, AgentSettings(anthropic_api_key="")),
        session_id=str(run.session.id),
        run_id=str(run.run_id),
        user_message="x",
    )


# Item 2: any failure before or while a run starts settles it.


async def test_missing_llm_key_fails_the_run_and_shows_an_error(
    run: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    sink = InMemoryEventSink(str(run.run_id))
    await run_agent_turn(
        _ctx(db_session, redis, AgentSettings(anthropic_api_key=""), event_sink=sink),
        session_id=str(run.session.id),
        run_id=str(run.run_id),
        user_message="x",
    )

    assert sink.events[-1]["type"] == "error" and sink.events[-1]["code"] == "internal"
    await _assert_released(db_session, run)


async def test_redis_failure_before_the_run_settles_the_session(
    run: SimpleNamespace, db_session: AsyncSession
) -> None:
    llm = FakeLLM(script=[FakeLLM.respond_text("hi")])
    await run_agent_turn(
        _ctx(db_session, _DownRedis(), AgentSettings(), llm_client=llm),
        session_id=str(run.session.id),
        run_id=str(run.run_id),
        user_message="x",
    )

    assert llm.calls == []
    await _assert_released(db_session, run)


async def test_a_message_after_a_failed_setup_starts_a_new_run(
    run: SimpleNamespace,
    db_session: AsyncSession,
    redis: Any,
    async_client: AsyncClient,
    enqueuer: _FakeEnqueuer,
) -> None:
    await _run_turn_without_key(db_session, run, redis)

    r = await async_client.post(
        f"{API}/{run.project.id}/agent/sessions/{run.session.id}/messages",
        json={"content": "again"},
        headers=run.headers,
    )
    assert r.status_code == 202  # not 409 run_active
    assert len(enqueuer.calls) == 1


# Item 3: a run that stopped making progress is reaped by the next message.


async def test_a_queued_run_without_progress_is_reaped_by_the_next_message(
    run: SimpleNamespace,
    db_session: AsyncSession,
    async_client: AsyncClient,
    redis: Any,
    enqueuer: _FakeEnqueuer,
) -> None:
    old_run = run.run_id
    r = await async_client.post(
        f"{API}/{run.project.id}/agent/sessions/{run.session.id}/messages",
        json={"content": "again"},
        headers=run.headers,
    )
    assert r.status_code == 202
    assert UUID(r.json()["run_id"]) != old_run
    # The stalled run's panel gets a terminal error, replayed to late subscribers.
    replay = json.loads(await redis.get(last_event_key(old_run)))
    assert replay["type"] == "error" and replay["code"] == "timeout"


async def test_a_run_with_recent_progress_still_blocks_a_message(
    run: SimpleNamespace, async_client: AsyncClient, redis: Any, enqueuer: _FakeEnqueuer
) -> None:
    await redis.set(f"agent:run:{run.run_id}:beat", b"1", ex=600)

    r = await async_client.post(
        f"{API}/{run.project.id}/agent/sessions/{run.session.id}/messages",
        json={"content": "again"},
        headers=run.headers,
    )
    assert r.status_code == 409


async def test_reaping_a_crashed_run_frees_its_concurrency_slot(
    run: SimpleNamespace,
    db_session: AsyncSession,
    async_client: AsyncClient,
    redis: Any,
    enqueuer: _FakeEnqueuer,
) -> None:
    # The worker that ran this turn took the user's slot, then died without giving it back.
    await acquire_run(redis, user_id=run.owner.id, project_id=run.project.id, now=_NOW)
    await redis.set(f"agent:run:{run.run_id}:slot", b"1")
    run.session.run_state = AgentRunState.running.value
    await db_session.commit()
    assert int(await redis.get(f"agent:conc:user:{run.owner.id}")) == 1

    r = await async_client.post(
        f"{API}/{run.project.id}/agent/sessions/{run.session.id}/messages",
        json={"content": "again"},
        headers=run.headers,
    )
    assert r.status_code == 202
    assert int(await redis.get(f"agent:conc:user:{run.owner.id}")) == 0


async def test_a_job_for_a_run_that_is_no_longer_active_does_nothing(
    run: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    """A reaped run's job may start late; it must not touch the session's newer run."""
    llm = FakeLLM(script=[FakeLLM.respond_text("hi")])
    stale = uuid4()
    await run_agent_turn(
        _ctx(db_session, redis, AgentSettings(), llm_client=llm, event_sink=InMemoryEventSink(str(stale))),
        session_id=str(run.session.id),
        run_id=str(stale),
        user_message="x",
    )

    assert llm.calls == []
    row = await _state(db_session, run)
    assert row.active_run_id == run.run_id
    assert row.run_state == AgentRunState.queued.value


async def test_progress_events_refresh_the_run_heartbeat(
    run: SimpleNamespace, db_session: AsyncSession, redis: Any
) -> None:
    llm = FakeLLM(script=[FakeLLM.respond_text("hi")])
    await run_agent_turn(
        _ctx(db_session, redis, AgentSettings(), llm_client=llm),
        session_id=str(run.session.id),
        run_id=str(run.run_id),
        user_message="x",
    )

    assert await redis.exists(f"agent:run:{run.run_id}:beat") == 1
