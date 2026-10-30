"""The auth module: users, credentials, login and the current-user dependencies."""

from inkstave.modules.auth.models.user import User
from inkstave.modules.auth.schemas.user import RegisterRequest, UserPublic
from inkstave.modules.auth.credentials.opaque_tokens import generate_token, hash_token
from inkstave.modules.auth.credentials.password import PasswordHasher
from inkstave.modules.auth.credentials.tokens import TokenService, build_token_service
from inkstave.modules.auth.deps import (
    NotAuthenticatedError,
    authenticate_ws_token,
    bearer_scheme,
    get_current_user,
    get_password_hasher,
    get_token_service,
    require_admin,
    sse_user,
)
from inkstave.modules.auth.accounts.users import normalise_email
from inkstave.modules.auth.throttling.policies import rate_limit_named

__all__ = [
    "NotAuthenticatedError",
    "PasswordHasher",
    "RegisterRequest",
    "TokenService",
    "User",
    "UserPublic",
    "authenticate_ws_token",
    "bearer_scheme",
    "build_token_service",
    "generate_token",
    "get_current_user",
    "get_password_hasher",
    "get_token_service",
    "hash_token",
    "normalise_email",
    "rate_limit_named",
    "require_admin",
    "sse_user",
]
