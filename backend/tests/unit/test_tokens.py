"""Unit tests for the JWT token service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest

from inkstave.auth.tokens import TokenError, build_token_service
from inkstave.config import Settings, get_settings
from inkstave.db.models.user import User


def _user(*, is_admin: bool = False) -> User:
    return User(
        id=uuid4(),
        email="user@example.com",
        hashed_password="x",
        display_name="User",
        is_admin=is_admin,
    )


def test_access_token_roundtrip_and_claims() -> None:
    svc = build_token_service(get_settings())
    user = _user(is_admin=True)
    token, expires_in = svc.create_access_token(user)
    claims = svc.decode_token(token, "access")
    assert claims["sub"] == str(user.id)
    assert claims["type"] == "access"
    assert claims["is_admin"] is True
    assert expires_in == get_settings().access_token_ttl_seconds
    assert claims["exp"] - claims["iat"] == expires_in


def test_refresh_token_roundtrip_and_claims() -> None:
    svc = build_token_service(get_settings())
    user_id, family_id = uuid4(), uuid4()
    token, jti = svc.create_refresh_token(user_id, family_id)
    claims = svc.decode_token(token, "refresh")
    assert claims["sub"] == str(user_id)
    assert claims["type"] == "refresh"
    assert claims["family_id"] == str(family_id)
    assert claims["jti"] == jti


def test_decode_rejects_wrong_type() -> None:
    svc = build_token_service(get_settings())
    access, _ = svc.create_access_token(_user())
    with pytest.raises(TokenError):
        svc.decode_token(access, "refresh")


def test_decode_rejects_bad_signature() -> None:
    svc = build_token_service(get_settings())
    forged = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "jti": uuid4().hex,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": get_settings().jwt_issuer,
        },
        "a-different-secret-also-32-bytes-long-xxxxx",
        algorithm="HS256",
    )
    with pytest.raises(TokenError):
        svc.decode_token(forged, "access")


def test_decode_rejects_expired() -> None:
    settings = get_settings()
    svc = build_token_service(settings)
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",
            "family_id": str(uuid4()),
            "jti": uuid4().hex,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "iss": settings.jwt_issuer,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        svc.decode_token(expired, "refresh")


def test_sub_is_a_uuid() -> None:
    svc = build_token_service(get_settings())
    user = _user()
    token, _ = svc.create_access_token(user)
    claims = svc.decode_token(token, "access")
    assert UUID(claims["sub"]) == user.id


def _sign(secret: str, issuer: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "is_admin": False,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": uuid4().hex,
            "iss": issuer,
        },
        secret,
        algorithm="HS256",
    )


def test_decode_accepts_a_previous_secret_during_rotation() -> None:
    # A token signed with the retired secret still verifies while it is listed
    # in jwt_secret_previous; the new secret is used for signing.
    old_secret = "retired-secret-0123456789abcdef-rotation"
    rotated = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret="brand-new-current-secret-0123456789abcdef",
        jwt_secret_previous=[old_secret],
    )
    svc = build_token_service(rotated)

    claims = svc.decode_token(_sign(old_secret, rotated.jwt_issuer), "access")
    assert claims["type"] == "access"

    with pytest.raises(TokenError):
        svc.decode_token(
            _sign("an-entirely-unknown-secret-aaaaaaaaaaaa", rotated.jwt_issuer), "access"
        )
