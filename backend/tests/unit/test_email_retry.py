"""send_email_job retries transient send failures through ARQ's Retry (spec 39).

ARQ retries a job only when it raises ``arq.Retry``; any other exception is a final failure, so
``max_tries=3`` alone never retries. A permanent refusal (a 4xx that is not 429) must not retry.
"""

from __future__ import annotations

from typing import Any

import aiosmtplib
import httpx
import pytest
from arq import Retry

from inkstave.core.config.settings import get_settings
from inkstave.infra.mailer.jobs import send_email_job

_INVITE = {
    "project_name": "Paper",
    "inviter_name": "Ada",
    "role": "editor",
    "accept_url": "http://x/i/t",
}


class _RaisingSender:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def send(self, email: Any) -> None:
        raise self._exc


def _status_error(status: int) -> httpx.HTTPStatusError:
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.resend.com/emails"))
    with pytest.raises(httpx.HTTPStatusError) as info:
        response.raise_for_status()
    return info.value


async def _send(exc: BaseException, job_try: int | None = None) -> None:
    ctx: dict[str, Any] = {"settings": get_settings(), "email_sender": _RaisingSender(exc)}
    if job_try is not None:
        ctx["job_try"] = job_try
    await send_email_job(ctx, template="project_invite", to="bob@example.com", context=_INVITE)


TRANSIENT: list[BaseException] = [
    httpx.ConnectError("connection refused"),
    httpx.ReadTimeout("slow"),
    _status_error(429),
    _status_error(500),
    _status_error(503),
    aiosmtplib.SMTPServerDisconnected("connection lost"),
    aiosmtplib.SMTPTimeoutError("timed out"),
    aiosmtplib.SMTPResponseException(421, "service not available"),
]

PERMANENT: list[BaseException] = [
    _status_error(400),
    _status_error(422),
    aiosmtplib.SMTPResponseException(550, "mailbox unavailable"),
    ValueError("bad template context"),
]


@pytest.mark.parametrize("exc", TRANSIENT, ids=lambda e: type(e).__name__)
async def test_transient_failure_asks_arq_to_retry(exc: BaseException) -> None:
    with pytest.raises(Retry) as info:
        await _send(exc, job_try=1)
    assert info.value.defer_score is not None
    assert info.value.defer_score > 0


async def test_retry_backs_off_between_attempts() -> None:
    with pytest.raises(Retry) as first:
        await _send(httpx.ConnectError("down"), job_try=1)
    with pytest.raises(Retry) as second:
        await _send(httpx.ConnectError("down"), job_try=2)
    assert first.value.defer_score is not None and second.value.defer_score is not None
    assert second.value.defer_score > first.value.defer_score


async def test_missing_job_try_counts_as_the_first_attempt() -> None:
    with pytest.raises(Retry):
        await _send(httpx.ConnectError("down"))


@pytest.mark.parametrize("exc", PERMANENT, ids=lambda e: type(e).__name__)
async def test_permanent_failure_is_not_retried(exc: BaseException) -> None:
    with pytest.raises(type(exc)) as info:
        await _send(exc, job_try=1)
    assert not isinstance(info.value, Retry)
