"""The email ARQ job (spec 39): render a template and send via the configured sender.

Handlers never send inline — they enqueue this job. On a transient send failure it
re-raises so ARQ retries per its policy; re-sending on retry is acceptable.

NOTE (spec 68 #126): spec 33 asked only for a no-op invite-email ARQ *stub*. The
full spec-39 email pipeline (``send_email_job``, ``EmailEnqueuer``,
``SmtpEmailSender``/``ConsoleEmailSender``, template rendering) was implemented
ahead of schedule during spec 33. This is intentional forward-scope over-delivery:
spec 39 legitimately supersedes the spec-33 stub requirement — do not regress it.
"""

from __future__ import annotations

import logging
from typing import Any

from inkstave.mailer.sender import OutgoingEmail, get_email_sender
from inkstave.mailer.templates import render_email

logger = logging.getLogger("inkstave.mailer")


async def send_email_job(
    ctx: dict[str, Any], *, template: str, to: str, context: dict[str, Any]
) -> dict[str, Any]:
    settings = ctx["settings"]
    sender = ctx.get("email_sender") or get_email_sender(settings)
    subject, text_body, html_body = render_email(template, context)
    try:
        await sender.send(
            OutgoingEmail(to=to, subject=subject, text_body=text_body, html_body=html_body)
        )
    except Exception:
        logger.exception("email_send_failed: template=%s to=%s", template, to)
        raise  # let ARQ retry
    return {"status": "sent", "template": template, "to": to}
