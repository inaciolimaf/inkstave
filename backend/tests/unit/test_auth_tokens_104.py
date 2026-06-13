"""Unit tests for the spec-104 token store and the magic_login template.

The token service touches the DB, so these use the transactional ``db_session``
fixture; expiry is driven by a FrozenClock (no real sleeps). The raw token must
never be persisted or logged.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.auth_token import AuthToken
from inkstave.db.models.user import User
from inkstave.errors import BadRequestError, GoneError
from inkstave.mailer.templates import render_email
from inkstave.services.auth_tokens import consume_token, issue_token
from inkstave.services.sharing_common import hash_token
from tests.factories.user import UserFactory
from tests.unit._clock import FrozenClock

pytestmark = pytest.mark.integration


async def _user(db: AsyncSession) -> User:
    return await UserFactory.create(db)


async def test_issue_stores_only_the_hash_and_expiry(db_session: AsyncSession) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    issued = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="email_verify",
        ttl_seconds=3600,
        clock=clock,
    )

    row = issued.token
    assert row.token_hash == hash_token(issued.raw)
    assert row.expires_at == clock.now() + timedelta(seconds=3600)
    assert row.consumed_at is None
    # The raw token appears in no column.
    for value in (row.purpose, str(row.user_id), row.email, row.token_hash):
        assert issued.raw not in value


async def test_issue_invalidates_older_same_purpose_tokens(db_session: AsyncSession) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    first = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="magic_login",
        ttl_seconds=600,
        clock=clock,
    )
    second = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="magic_login",
        ttl_seconds=600,
        clock=clock,
    )

    # The first token is now spent; only the second verifies.
    await db_session.refresh(first.token)
    assert first.token.consumed_at is not None
    with pytest.raises(BadRequestError):
        await consume_token(db_session, raw_token=first.raw, purpose="magic_login", clock=clock)
    consumed = await consume_token(
        db_session, raw_token=second.raw, purpose="magic_login", clock=clock
    )
    assert consumed.id == second.token.id


async def test_consume_happy_path_then_single_use(db_session: AsyncSession) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    issued = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="password_reset",
        ttl_seconds=3600,
        clock=clock,
    )

    row = await consume_token(
        db_session, raw_token=issued.raw, purpose="password_reset", clock=clock
    )
    assert row.consumed_at == clock.now()
    # Replay → BadRequest (single-use).
    with pytest.raises(BadRequestError):
        await consume_token(db_session, raw_token=issued.raw, purpose="password_reset", clock=clock)


async def test_consume_wrong_purpose_is_bad_request(db_session: AsyncSession) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    issued = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="email_verify",
        ttl_seconds=3600,
        clock=clock,
    )
    with pytest.raises(BadRequestError):
        await consume_token(db_session, raw_token=issued.raw, purpose="magic_login", clock=clock)


async def test_consume_unknown_token_is_bad_request(db_session: AsyncSession) -> None:
    with pytest.raises(BadRequestError):
        await consume_token(db_session, raw_token="not-a-real-token", purpose="email_verify")


async def test_consume_expired_is_gone_and_not_consumed(db_session: AsyncSession) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    issued = await issue_token(
        db_session,
        user_id=user.id,
        email=user.email,
        purpose="email_verify",
        ttl_seconds=60,
        clock=clock,
    )
    clock.advance(seconds=61)
    with pytest.raises(GoneError):
        await consume_token(db_session, raw_token=issued.raw, purpose="email_verify", clock=clock)
    # The expired token was not consumed (still redeemable were it not expired).
    row = await db_session.scalar(select(AuthToken).where(AuthToken.id == issued.token.id))
    assert row is not None and row.consumed_at is None


async def test_raw_token_never_logged(
    db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FrozenClock()
    user = await _user(db_session)
    with caplog.at_level(logging.INFO):
        issued = await issue_token(
            db_session,
            user_id=user.id,
            email=user.email,
            purpose="email_verify",
            ttl_seconds=3600,
            clock=clock,
        )
        await consume_token(db_session, raw_token=issued.raw, purpose="email_verify", clock=clock)
    assert issued.raw not in caplog.text
    assert issued.token.token_hash not in caplog.text


def test_magic_login_template_renders_and_escapes() -> None:
    magic_url = "http://localhost:5173/magic-link?token=abc&x=<script>"
    subject, text, html = render_email("magic_login", {"user_name": "Ada", "magic_url": magic_url})
    assert subject
    assert text and html
    assert magic_url in text  # text body keeps the raw URL
    # HTML body escapes every interpolated value (spec-40 XSS rule).
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Ada" in html
