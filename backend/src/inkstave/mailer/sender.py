"""Email senders (spec 39): SMTP for prod, console/file for dev + tests.

Selected by ``EMAIL_BACKEND`` via :func:`get_email_sender` and injected through DI,
so tests swap in a capturing fake. No sender opens a real SMTP connection unless it
is the SMTP backend actually sending.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from inkstave.config import Settings

logger = logging.getLogger("inkstave.mailer")


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_addr: str | None = None


@runtime_checkable
class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None: ...


class ConsoleEmailSender:
    """Logs the rendered email at INFO; sends nothing."""

    def __init__(self, default_from: str) -> None:
        self._default_from = default_from

    async def send(self, email: OutgoingEmail) -> None:
        logger.info(
            "email_console: from=%s to=%s subject=%r\n%s",
            email.from_addr or self._default_from,
            email.to,
            email.subject,
            email.text_body,
        )


class FileEmailSender:
    """Writes one JSON file per email to ``EMAIL_FILE_DIR`` for local inspection/tests."""

    def __init__(self, directory: str, default_from: str) -> None:
        self._dir = Path(directory)
        self._default_from = default_from

    async def send(self, email: OutgoingEmail) -> None:
        # Serialise in-memory (cheap) on the loop, then offload the blocking
        # filesystem I/O so it never stalls the event loop (spec 93).
        payload = json.dumps(
            {
                "from": email.from_addr or self._default_from,
                "to": email.to,
                "subject": email.subject,
                "text_body": email.text_body,
                "html_body": email.html_body,
            },
            indent=2,
        )
        path = self._dir / f"{uuid.uuid4().hex}.json"
        await asyncio.to_thread(self._dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, payload, encoding="utf-8")


class SmtpEmailSender:
    """Sends via async SMTP (aiosmtplib). Raises on failure so the job can retry."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        use_tls: bool,
        default_from: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._use_tls = use_tls
        self._default_from = default_from

    async def send(self, email: OutgoingEmail) -> None:
        from email.message import EmailMessage  # stdlib (this package is `mailer`)

        import aiosmtplib

        message = EmailMessage()
        message["From"] = email.from_addr or self._default_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text_body)
        if email.html_body is not None:
            message.add_alternative(email.html_body, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=self._host,
            port=self._port,
            username=self._user or None,
            password=self._password or None,
            start_tls=self._use_tls,
        )


class ResendEmailSender:
    """Sends via the Resend HTTP API. Raises on failure so the ARQ job retries.

    Opens no connection at construction (cheap to build in DI / tests). Never logs
    the API key; logs the Resend message id at DEBUG on success.
    """

    def __init__(
        self,
        *,
        api_key: str,
        default_from: str,
        base_url: str = "https://api.resend.com",
        timeout_s: float = 10.0,
        transport: object | None = None,
    ) -> None:
        self._api_key = api_key
        self._default_from = default_from
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        # An injected httpx transport (e.g. httpx.MockTransport) keeps tests
        # network-free; production leaves it None (a real connection).
        self._transport = transport

    async def send(self, email: OutgoingEmail) -> None:
        import httpx

        payload: dict[str, object] = {
            "from": email.from_addr or self._default_from,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text_body,
        }
        if email.html_body is not None:
            payload["html"] = email.html_body

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s,
                transport=self._transport,  # type: ignore[arg-type]
            ) as client:
                response = await client.post(
                    f"{self._base_url}/emails",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            # Transport error / timeout — log without the key, then propagate so ARQ retries.
            logger.warning("email_resend_transport_error: to=%s error=%s", email.to, exc)
            raise

        if response.status_code >= 400:
            # Surface the HTTP status + any error body (never the key) and raise to retry.
            logger.warning(
                "email_resend_http_error: to=%s status=%s body=%s",
                email.to,
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()

        message_id = ""
        try:
            message_id = str(response.json().get("id", ""))
        except ValueError:  # non-JSON 2xx body — fine, just no id to log
            pass
        logger.debug("email_resend_sent: to=%s id=%s", email.to, message_id)


def get_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "resend":
        return ResendEmailSender(
            api_key=settings.resend_api_key,
            default_from=settings.email_from,
        )
    if settings.email_backend == "smtp":
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            default_from=settings.email_from,
        )
    if settings.email_backend == "file":
        return FileEmailSender(settings.email_file_dir, settings.email_from)
    return ConsoleEmailSender(settings.email_from)
