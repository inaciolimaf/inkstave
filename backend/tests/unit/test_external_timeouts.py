"""No wait without a deadline: Redis, SMTP, S3, and the work that must outlive the DB limits."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from inkstave.core.config.settings import Settings
from inkstave.infra.mailer.sender import OutgoingEmail, SmtpEmailSender, get_email_sender
from inkstave.infra.redis import create_redis_pool
from inkstave.infra.storage.factory import get_object_store
from inkstave.modules.agent.graph import runner as agent_runner
from inkstave.modules.collab.ws.redis_bridge import RedisBridge
from tests.unit.test_compile_service import FakeRunner, build_service, ok_outcome

BACKEND = Path(__file__).resolve().parents[2]


async def test_redis_client_carries_both_timeouts() -> None:
    client = await create_redis_pool("redis://127.0.0.1:1/0", connect_timeout_s=2.0, socket_timeout_s=4.0)
    try:
        kwargs = client.connection_pool.connection_kwargs
        assert kwargs["socket_connect_timeout"] == 2.0
        assert kwargs["socket_timeout"] == 4.0
    finally:
        await client.aclose()


async def test_collab_reader_survives_a_quiet_channel_polling_below_the_socket_timeout() -> None:
    reached_the_message = asyncio.Event()
    stop = asyncio.Event()
    socket_timeout = Settings(_env_file=None).redis_socket_timeout_s  # type: ignore[call-arg]

    class PollingPubSub:
        def __init__(self) -> None:
            self.replies: list[Any] = [None, None, {"type": "subscribe", "data": 1}]

        async def get_message(self, *, timeout: float) -> Any:  # noqa: ASYNC109
            assert timeout < socket_timeout
            if self.replies:
                return self.replies.pop(0)
            reached_the_message.set()
            await stop.wait()
            return None

    bridge = RedisBridge(SimpleNamespace(), "instance", "collab:")  # type: ignore[arg-type]
    task = asyncio.create_task(bridge._reader(PollingPubSub(), None))  # type: ignore[arg-type]
    async with asyncio.timeout(1):
        await reached_the_message.wait()
    task.cancel()


async def test_smtp_send_has_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import aiosmtplib

    seen: dict[str, Any] = {}

    async def fake_send(_message: Any, **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(aiosmtplib, "send", fake_send)
    sender = SmtpEmailSender(
        host="h", port=25, user="", password="", use_tls=False, default_from="a@b.c", timeout_s=7.0
    )

    await sender.send(OutgoingEmail(to="x@y.z", subject="s", text_body="t"))

    assert seen["timeout"] == 7.0


def test_settings_reach_the_smtp_sender() -> None:
    settings = Settings(_env_file=None, email_backend="smtp", smtp_timeout_s=9.0)  # type: ignore[call-arg]
    assert get_email_sender(settings)._timeout_s == 9.0  # type: ignore[attr-defined]


def test_s3_client_gets_explicit_timeouts() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, file_storage_backend="s3", s3_bucket="b", s3_connect_timeout_s=2, s3_read_timeout_s=8
    )
    config = get_object_store(settings)._client_kwargs["config"]  # type: ignore[attr-defined]
    assert config.connect_timeout == 2
    assert config.read_timeout == 8
    assert config.retries["total_max_attempts"] == 2


def test_idle_limit_stays_above_the_slowest_call_inside_a_request() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    per_attempt = settings.s3_connect_timeout_s + settings.s3_read_timeout_s
    assert settings.db_idle_in_transaction_timeout_s > per_attempt * 2


async def test_the_compile_ends_its_transaction_before_tectonic_runs(tmp_path: Path) -> None:
    from inkstave.modules.compile.running.service import CompileOptions

    events: list[str] = []
    runner = FakeRunner(ok_outcome(), {"main.pdf": b"%PDF-1.7"})
    original_run = runner.run

    async def run(**kwargs: Any) -> Any:
        events.append("tectonic")
        return await original_run(**kwargs)

    runner.run = run  # type: ignore[method-assign]
    service = build_service(tmp_path, runner, [("main.tex", "hi")])

    async def assembled() -> None:
        events.append("commit")

    service._on_assembled = assembled

    await service.compile(CompileOptions(project_id=uuid4()))

    assert events == ["commit", "tectonic"]


async def test_the_agent_turn_raises_its_idle_limit_first(monkeypatch: pytest.MonkeyPatch) -> None:
    class StopError(Exception):
        pass

    seen: list[int] = []

    async def fake_allow_idle(_db: Any, seconds: int) -> None:
        seen.append(seconds)
        raise StopError

    monkeypatch.setattr(agent_runner, "allow_idle", fake_allow_idle)
    deps = SimpleNamespace(settings=SimpleNamespace(agent_job_timeout_s=600))

    with pytest.raises(StopError):
        await agent_runner.run_turn(session=None, user_message="hi", deps=deps, db=None)  # type: ignore[arg-type]

    assert seen == [600]


@pytest.mark.parametrize("name", ["migrations/env.py", "src/inkstave/modules/admin/provisioning/migrate.py"])
def test_migrations_do_not_inherit_the_request_limits(name: str) -> None:
    # A long ALTER or a blocked advisory lock must not be killed by the statement timeout.
    source = (BACKEND / name).read_text(encoding="utf-8")
    assert "create_engine_and_sessionmaker" not in source
    assert "server_settings" not in source
