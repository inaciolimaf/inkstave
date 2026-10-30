"""Pluggable async email: senders, templates, enqueuer, and the ARQ send job (spec 39)."""

from inkstave.infra.mailer.sender import (
    ConsoleEmailSender,
    EmailSender,
    FileEmailSender,
    OutgoingEmail,
    ResendEmailSender,
    SmtpEmailSender,
    get_email_sender,
)
from inkstave.infra.mailer.templates import render_email

__all__ = [
    "ConsoleEmailSender",
    "EmailSender",
    "FileEmailSender",
    "OutgoingEmail",
    "ResendEmailSender",
    "SmtpEmailSender",
    "get_email_sender",
    "render_email",
]
