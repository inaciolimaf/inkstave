"""Pluggable async email: senders, templates, enqueuer, and the ARQ send job (spec 39)."""

from inkstave.mailer.sender import (
    ConsoleEmailSender,
    EmailSender,
    FileEmailSender,
    OutgoingEmail,
    SmtpEmailSender,
    get_email_sender,
)
from inkstave.mailer.templates import render_email

__all__ = [
    "ConsoleEmailSender",
    "EmailSender",
    "FileEmailSender",
    "OutgoingEmail",
    "SmtpEmailSender",
    "get_email_sender",
    "render_email",
]
