"""Unit tests for the send_email_job ARQ job (spec 39)."""

from __future__ import annotations

from typing import Any

import pytest

from inkstave.config import get_settings
from inkstave.mailer.jobs import send_email_job
from inkstave.mailer.sender import OutgoingEmail


class _CapturingSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)


class _FailingSender:
    async def send(self, email: OutgoingEmail) -> None:
        raise RuntimeError("smtp temporarily unavailable")


def _ctx(sender: Any) -> dict[str, Any]:
    return {"settings": get_settings(), "email_sender": sender}


async def test_job_renders_and_sends_via_injected_sender() -> None:
    sender = _CapturingSender()
    result = await send_email_job(
        _ctx(sender),
        template="project_invite",
        to="bob@example.com",
        context={
            "project_name": "Paper",
            "inviter_name": "Ada",
            "role": "editor",
            "accept_url": "http://x/invite/tok",
        },
    )
    assert result["status"] == "sent"
    assert len(sender.sent) == 1
    email = sender.sent[0]
    assert email.to == "bob@example.com"
    assert "Paper" in email.subject and "http://x/invite/tok" in email.text_body


async def test_job_reraises_on_send_failure() -> None:
    # criterion 10: a transient failure propagates so ARQ retries.
    with pytest.raises(RuntimeError):
        await send_email_job(
            _ctx(_FailingSender()),
            template="project_invite",
            to="bob@example.com",
            context={
                "project_name": "P",
                "inviter_name": "A",
                "role": "editor",
                "accept_url": "http://x/i/t",
            },
        )
