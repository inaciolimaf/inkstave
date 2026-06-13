"""Email templates (spec 39). Subjects/bodies are Inkstave's own — never copied."""

from __future__ import annotations

from html import escape
from typing import Any


class UnknownTemplateError(Exception):
    def __init__(self, template: str) -> None:
        super().__init__(f"unknown email template: {template}")


def _project_invite(ctx: dict[str, Any]) -> tuple[str, str, str]:
    project = ctx["project_name"]
    inviter = ctx["inviter_name"]
    role = ctx["role"]
    accept_url = ctx["accept_url"]
    subject = f"{inviter} invited you to {project} on Inkstave"
    text = (
        f"{inviter} has invited you to collaborate on “{project}” as a {role}.\n\n"
        f"Accept the invitation:\n{accept_url}\n\n"
        "If you didn’t expect this, you can ignore this email.\n"
    )
    # Escape user-controlled values (project/inviter names) in the HTML body (spec 40).
    html = (
        f"<p>{escape(str(inviter))} has invited you to collaborate on "
        f"<strong>{escape(str(project))}</strong> as a {escape(str(role))}.</p>"
        f'<p><a href="{escape(str(accept_url), quote=True)}">Accept the invitation</a></p>'
        "<p>If you didn’t expect this, you can ignore this email.</p>"
    )
    return subject, text, html


def _password_reset(ctx: dict[str, Any]) -> tuple[str, str, str]:
    name = ctx.get("user_name", "there")
    reset_url = ctx["reset_url"]
    subject = "Reset your Inkstave password"
    text = (
        f"Hi {name},\n\nWe received a request to reset your Inkstave password.\n\n"
        f"Reset it here:\n{reset_url}\n\n"
        "If you didn’t request this, you can ignore this email.\n"
    )
    html = (
        f"<p>Hi {escape(str(name))},</p>"
        "<p>We received a request to reset your Inkstave password.</p>"
        f'<p><a href="{escape(str(reset_url), quote=True)}">Reset your password</a></p>'
        "<p>If you didn’t request this, you can ignore this email.</p>"
    )
    return subject, text, html


def _email_change_confirmation(ctx: dict[str, Any]) -> tuple[str, str, str]:
    name = ctx.get("user_name", "there")
    confirm_url = ctx["confirm_url"]
    subject = "Confirm your new Inkstave email"
    text = (
        f"Hi {name},\n\nWe received a request to change your Inkstave email to this "
        f"address.\n\nConfirm the change:\n{confirm_url}\n\n"
        "If you didn’t request this, you can ignore this email — nothing will change.\n"
    )
    html = (
        f"<p>Hi {escape(str(name))},</p>"
        "<p>We received a request to change your Inkstave email to this address.</p>"
        f'<p><a href="{escape(str(confirm_url), quote=True)}">Confirm the change</a></p>'
        "<p>If you didn’t request this, you can ignore this email — nothing will change.</p>"
    )
    return subject, text, html


def _email_verification(ctx: dict[str, Any]) -> tuple[str, str, str]:
    name = ctx.get("user_name", "there")
    verify_url = ctx["verify_url"]
    subject = "Verify your Inkstave email"
    text = (
        f"Hi {name},\n\nWelcome to Inkstave! Please confirm this is your email "
        f"address.\n\nVerify your email:\n{verify_url}\n\n"
        "If you didn’t create an Inkstave account, you can ignore this email.\n"
    )
    html = (
        f"<p>Hi {escape(str(name))},</p>"
        "<p>Welcome to Inkstave! Please confirm this is your email address.</p>"
        f'<p><a href="{escape(str(verify_url), quote=True)}">Verify your email</a></p>'
        "<p>If you didn’t create an Inkstave account, you can ignore this email.</p>"
    )
    return subject, text, html


def _magic_login(ctx: dict[str, Any]) -> tuple[str, str, str]:
    name = ctx.get("user_name", "there")
    magic_url = ctx["magic_url"]
    subject = "Your Inkstave sign-in link"
    text = (
        f"Hi {name},\n\nHere is your one-time link to sign in to Inkstave.\n\n"
        f"Sign in:\n{magic_url}\n\n"
        "If you didn’t request this, you can ignore this email.\n"
    )
    html = (
        f"<p>Hi {escape(str(name))},</p>"
        "<p>Here is your one-time link to sign in to Inkstave.</p>"
        f'<p><a href="{escape(str(magic_url), quote=True)}">Sign in to Inkstave</a></p>'
        "<p>If you didn’t request this, you can ignore this email.</p>"
    )
    return subject, text, html


_TEMPLATES = {
    "project_invite": _project_invite,
    "password_reset": _password_reset,
    "email_change_confirmation": _email_change_confirmation,
    "email_verification": _email_verification,
    "magic_login": _magic_login,
}


def render_email(template: str, context: dict[str, Any]) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for ``template`` rendered with ``context``."""
    renderer = _TEMPLATES.get(template)
    if renderer is None:
        raise UnknownTemplateError(template)
    return renderer(context)
