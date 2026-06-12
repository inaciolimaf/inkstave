"""Unit tests for the email sender factory + templates (spec 39)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inkstave.config import get_settings
from inkstave.mailer.sender import (
    ConsoleEmailSender,
    FileEmailSender,
    OutgoingEmail,
    SmtpEmailSender,
    get_email_sender,
)
from inkstave.mailer.templates import UnknownTemplateError, render_email


def _settings(**over: object):
    return get_settings().model_copy(update=over)


def test_factory_selects_backend() -> None:
    assert isinstance(get_email_sender(_settings(email_backend="console")), ConsoleEmailSender)
    assert isinstance(get_email_sender(_settings(email_backend="file")), FileEmailSender)
    assert isinstance(get_email_sender(_settings(email_backend="smtp")), SmtpEmailSender)


async def test_file_sender_writes_one_file(tmp_path: Path) -> None:
    sender = FileEmailSender(str(tmp_path), "Inkstave <no-reply@x>")
    await sender.send(OutgoingEmail(to="bob@x.com", subject="Hi", text_body="hello"))
    files = list(tmp_path.glob("*.json"))  # noqa: ASYNC240
    assert len(files) == 1  # criterion 1: written, no SMTP
    data = json.loads(files[0].read_text())  # noqa: ASYNC240
    assert data["to"] == "bob@x.com" and data["subject"] == "Hi" and data["text_body"] == "hello"


async def test_console_sender_does_not_raise() -> None:
    await ConsoleEmailSender("from@x").send(OutgoingEmail(to="a@x", subject="s", text_body="b"))


def test_project_invite_template() -> None:
    subject, text, html = render_email(
        "project_invite",
        {
            "project_name": "Paper",
            "inviter_name": "Ada",
            "role": "editor",
            "accept_url": "http://x/invite/tok",
        },
    )
    assert "Ada" in subject and "Paper" in subject
    assert "editor" in text and "http://x/invite/tok" in text
    assert "http://x/invite/tok" in html


def test_password_reset_template() -> None:
    subject, text, _html = render_email("password_reset", {"reset_url": "http://x/reset/abc"})
    assert "password" in subject.lower()
    assert "http://x/reset/abc" in text


def test_project_invite_html_is_escaped() -> None:
    # spec 40: user-controlled project/inviter names must not inject HTML.
    _subject, text, html = render_email(
        "project_invite",
        {
            "project_name": "<img src=x onerror=alert(1)>",
            "inviter_name": "<b>Eve</b>",
            "role": "editor",
            "accept_url": "http://x/invite/tok",
        },
    )
    assert "<img" not in html and "<b>Eve</b>" not in html
    assert "&lt;img" in html and "&lt;b&gt;Eve" in html
    assert "<img src=x" in text  # plain-text body is left as-is


def test_unknown_template_raises() -> None:
    with pytest.raises(UnknownTemplateError):
        render_email("nope", {})
