"""Unit tests for the Resend sender, factory, verification template, CLI, validator (spec 103)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from inkstave.config import get_settings
from inkstave.mailer.sender import OutgoingEmail, ResendEmailSender, get_email_sender
from inkstave.mailer.templates import render_email


def _sender(handler: Any, key: str = "re_secret_key") -> ResendEmailSender:
    return ResendEmailSender(
        api_key=key,
        default_from="Inkstave <no-reply@x>",
        transport=httpx.MockTransport(handler),
    )


# --------------------------------------------------------------------------- #
# ResendEmailSender
# --------------------------------------------------------------------------- #


async def test_resend_posts_expected_payload() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "msg_123"})

    await _sender(handler).send(
        OutgoingEmail(to="bob@x.com", subject="Hi", text_body="hello", html_body="<p>hi</p>")
    )
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_secret_key"
    assert captured["body"] == {
        "from": "Inkstave <no-reply@x>",
        "to": ["bob@x.com"],
        "subject": "Hi",
        "text": "hello",
        "html": "<p>hi</p>",
    }


async def test_resend_omits_html_when_none() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "x"})

    await _sender(handler).send(OutgoingEmail(to="b@x.com", subject="S", text_body="t"))
    assert "html" not in captured["body"]
    assert captured["body"]["to"] == ["b@x.com"]  # to is a list


async def test_resend_raises_on_non_2xx_and_hides_key(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "invalid recipient"})

    with caplog.at_level(logging.WARNING):
        with pytest.raises(httpx.HTTPStatusError):
            await _sender(handler, key="re_TOPSECRET").send(
                OutgoingEmail(to="b@x.com", subject="s", text_body="t")
            )
    assert "re_TOPSECRET" not in caplog.text
    assert "422" in caplog.text  # status logged for the bounce


async def test_resend_raises_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.HTTPError):
        await _sender(handler).send(OutgoingEmail(to="b@x.com", subject="s", text_body="t"))


def test_factory_selects_resend_and_keeps_others() -> None:
    resend = get_settings().model_copy(update={"email_backend": "resend", "resend_api_key": "re_x"})
    assert isinstance(get_email_sender(resend), ResendEmailSender)
    # The existing backends are unchanged.
    from inkstave.mailer.sender import ConsoleEmailSender

    console = get_settings().model_copy(update={"email_backend": "console"})
    assert isinstance(get_email_sender(console), ConsoleEmailSender)


# --------------------------------------------------------------------------- #
# email_verification template
# --------------------------------------------------------------------------- #


def test_email_verification_template_renders_and_escapes() -> None:
    subject, text, html = render_email(
        "email_verification",
        {"user_name": "<b>Ann</b>", "verify_url": "http://x/verify?token=t&a=1"},
    )
    assert subject == "Verify your Inkstave email"
    assert text and html
    assert "http://x/verify?token=t&a=1" in text  # link present in text
    assert "&amp;a=1" in html  # URL escaped in the HTML href
    assert "&lt;b&gt;Ann" in html  # user name escaped (no raw tags)


# --------------------------------------------------------------------------- #
# send-test-email CLI
# --------------------------------------------------------------------------- #


class _FakeSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)


class _RaisingSender:
    async def send(self, email: OutgoingEmail) -> None:
        raise RuntimeError("smtp unreachable")


async def test_cli_send_test_email_pass(capsys: pytest.CaptureFixture[str]) -> None:
    from inkstave.cli import _cmd_send_test_email

    fake = _FakeSender()
    rc = await _cmd_send_test_email(to="a@b.com", template="email_verification", sender=fake)
    assert rc == 0
    assert len(fake.sent) == 1
    assert "PASS" in capsys.readouterr().out


async def test_cli_send_test_email_fail_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    from inkstave.cli import _cmd_send_test_email

    rc = await _cmd_send_test_email(
        to="a@b.com", template="email_verification", sender=_RaisingSender()
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "FAIL" in err and "Traceback" not in err


# --------------------------------------------------------------------------- #
# Config validator
# --------------------------------------------------------------------------- #


def test_validator_flags_missing_resend_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave.bootstrap.config_check import validate_config

    monkeypatch.setenv("EMAIL_BACKEND", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    try:
        problems = validate_config()
        assert any("RESEND_API_KEY" in p for p in problems)
    finally:
        get_settings.cache_clear()
