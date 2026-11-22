"""The email ARQ job (spec 39): render a template and send via the configured sender.

Handlers never send inline — they enqueue this job. A transient send failure (a network error,
a timeout, a 429 or 5xx from Resend, a 421 or a dropped connection from SMTP) raises ``arq.Retry``
with a backoff: ARQ retries only on ``Retry``, so ``max_tries`` alone never retries. A permanent
refusal is raised as is and ends the job. Re-sending on retry is acceptable.

NOTE (spec 68 #126): spec 33 asked only for a no-op invite-email ARQ *stub*. The
full spec-39 email pipeline (``send_email_job``, ``EmailEnqueuer``,
``SmtpEmailSender``/``ConsoleEmailSender``, template rendering) was implemented
ahead of schedule during spec 33. This is intentional forward-scope over-delivery:
spec 39 legitimately supersedes the spec-33 stub requirement — do not regress it.
"""

from __future__ import annotations

import logging
from typing import Any

import aiosmtplib
import httpx
from arq import Retry

from inkstave.infra.mailer.sender import OutgoingEmail, get_email_sender
from inkstave.infra.mailer.templates import render_email

logger = logging.getLogger("inkstave.mailer")

# Seconds before the second attempt; each further attempt doubles the wait.
RETRY_BASE_DELAY_S = 30


def _is_transient(exc: BaseException) -> bool:
    """True for a failure that a later attempt may not see: the network, the provider's side, a rate limit."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, aiosmtplib.SMTPResponseException):
        return 400 <= exc.code < 500  # SMTP 4xx is temporary by definition; 5xx is permanent
    return isinstance(
        exc,
        (
            httpx.TransportError,
            aiosmtplib.SMTPServerDisconnected,
            aiosmtplib.SMTPConnectError,
            aiosmtplib.SMTPTimeoutError,
            TimeoutError,
            ConnectionError,
        ),
    )


def _retry_delay(job_try: int) -> int:
    """Backoff for the attempt that just failed: 30 s, 60 s, 120 s, ..."""
    return RETRY_BASE_DELAY_S << max(job_try - 1, 0)  # a shift keeps it int; `2 ** n` types as Any


async def send_email_job(
    ctx: dict[str, Any], *, template: str, to: str, context: dict[str, Any]
) -> dict[str, Any]:
    settings = ctx["settings"]
    sender = ctx.get("email_sender") or get_email_sender(settings)
    subject, text_body, html_body = render_email(template, context)
    try:
        await sender.send(OutgoingEmail(to=to, subject=subject, text_body=text_body, html_body=html_body))
    except Exception as exc:
        logger.exception("email_send_failed: template=%s to=%s", template, to)
        if _is_transient(exc):
            raise Retry(defer=_retry_delay(int(ctx.get("job_try", 1)))) from exc
        raise
    return {"status": "sent", "template": template, "to": to}
