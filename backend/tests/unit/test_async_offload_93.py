"""CPU-bound / blocking calls run off the event loop via asyncio.to_thread (spec 93).

These lock in the *offload pattern* (the call still delegates to the real
to_thread so results stay correct) and confirm the file-sender output is
byte-identical. Behaviour is unchanged; only where the work runs.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


class _Result:
    def __init__(self, user: Any) -> None:
        self._user = user

    def scalar_one_or_none(self) -> Any:
        return self._user


class FakeSession:
    def __init__(self, user: Any = None) -> None:
        self._user = user

    async def execute(self, _stmt: Any) -> _Result:
        return _Result(self._user)


class FakeHasher:
    def __init__(self, *, ok: bool = True) -> None:
        self._ok = ok

    def verify(self, _plain: str, _hashed: str) -> bool:
        return self._ok

    def hash(self, _plain: str) -> str:
        return "$argon2id$dummy"


def _record_to_thread(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Patch asyncio.to_thread to record the offloaded callables, still delegating."""
    calls: list[Any] = []
    real = asyncio.to_thread

    async def recording(func: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(func)
        return await real(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", recording)
    return calls


async def test_login_verify_runs_via_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave.services.auth import authenticate_user

    calls = _record_to_thread(monkeypatch)
    hasher = FakeHasher(ok=True)
    user = SimpleNamespace(id=uuid4(), hashed_password="$argon2id$dummy")
    result = await authenticate_user(FakeSession(user), hasher, "u@example.com", "pw")
    assert result is user
    assert hasher.verify in calls  # the Argon2 verify was offloaded


async def test_missing_user_dummy_verify_runs_via_to_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from inkstave.services.auth import authenticate_user

    calls = _record_to_thread(monkeypatch)
    hasher = FakeHasher(ok=False)
    result = await authenticate_user(FakeSession(None), hasher, "missing@example.com", "pw")
    assert result is None  # timing mitigation: still verifies against the dummy hash
    assert hasher.verify in calls


async def test_file_email_sender_offloads_io_and_writes_identically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from inkstave.mailer.sender import FileEmailSender, OutgoingEmail

    calls = _record_to_thread(monkeypatch)
    mail_dir = tmp_path / "mail"
    sender = FileEmailSender(str(mail_dir), "noreply@inkstave.local")
    await sender.send(
        OutgoingEmail(to="a@b.com", subject="Hi", text_body="Body", html_body="<p>Body</p>")
    )

    files = list(mail_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data == {
        "from": "noreply@inkstave.local",
        "to": "a@b.com",
        "subject": "Hi",
        "text_body": "Body",
        "html_body": "<p>Body</p>",
    }
    offloaded = {getattr(f, "__name__", str(f)) for f in calls}
    assert {"mkdir", "write_text"} <= offloaded
