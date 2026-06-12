"""JWT access/refresh token service (HS256).

Access tokens are stateless and short-lived; refresh tokens are long-lived and
their server-side record (Redis) makes them revocable. The service signs with
the current ``jwt_secret`` and verifies against the current secret *and* any
``jwt_secret_previous`` entries, enabling zero-downtime secret rotation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

import jwt

from inkstave.time import SYSTEM_CLOCK, Clock

if TYPE_CHECKING:
    from inkstave.config import Settings
    from inkstave.db.models.user import User

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token cannot be decoded, is expired, or is the wrong type."""


class TokenService:
    """Signs and verifies JWTs from settings-driven configuration."""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret
        self._previous_secrets = list(settings.jwt_secret_previous)
        self._algorithm = settings.jwt_algorithm
        self._issuer = settings.jwt_issuer
        self._access_ttl = settings.access_token_ttl_seconds
        self._refresh_ttl = settings.refresh_token_ttl_seconds

    def _encode(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def create_access_token(self, user: User, *, clock: Clock = SYSTEM_CLOCK) -> tuple[str, int]:
        """Return ``(token, expires_in_seconds)`` for the user's access token."""
        now = clock.now()
        claims = {
            "sub": str(user.id),
            "type": "access",
            "is_admin": user.is_admin,
            "iss": self._issuer,
            "iat": now,
            "exp": now + timedelta(seconds=self._access_ttl),
            "jti": uuid4().hex,
        }
        return self._encode(claims), self._access_ttl

    def create_refresh_token(
        self, user_id: UUID, family_id: UUID, *, clock: Clock = SYSTEM_CLOCK
    ) -> tuple[str, str]:
        """Return ``(token, jti)`` for a refresh token in the given family."""
        now = clock.now()
        jti = uuid4().hex
        claims = {
            "sub": str(user_id),
            "type": "refresh",
            "family_id": str(family_id),
            "iss": self._issuer,
            "iat": now,
            "exp": now + timedelta(seconds=self._refresh_ttl),
            "jti": jti,
        }
        return self._encode(claims), jti

    def decode_token(self, token: str, expected_type: TokenType) -> dict[str, Any]:
        """Decode and validate a token; raise :class:`TokenError` on any problem."""
        last_error: Exception | None = None
        for secret in (self._secret, *self._previous_secrets):
            try:
                claims: dict[str, Any] = jwt.decode(
                    token,
                    secret,
                    algorithms=[self._algorithm],
                    issuer=self._issuer,
                    options={"require": ["exp", "iat", "sub", "type", "jti"]},
                )
            except jwt.PyJWTError as exc:
                last_error = exc
                continue
            if claims.get("type") != expected_type:
                raise TokenError(f"Expected a {expected_type} token")
            return claims
        raise TokenError(str(last_error) if last_error else "Invalid token")


def build_token_service(settings: Settings) -> TokenService:
    """Construct a :class:`TokenService` from settings."""
    return TokenService(settings)
