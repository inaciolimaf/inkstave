"""Argon2id password hashing.

A thin wrapper over ``argon2-cffi``'s :class:`~argon2.PasswordHasher`. The cost
parameters come from settings so tests can lower them (the hasher is built via
the :func:`inkstave.dependencies.get_password_hasher` dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argon2 import PasswordHasher as _Argon2Hasher

if TYPE_CHECKING:
    from inkstave.config import Settings


class PasswordHasher:
    """Hash and verify passwords with argon2id."""

    def __init__(self, *, time_cost: int, memory_cost: int, parallelism: int) -> None:
        self._hasher = _Argon2Hasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )

    def hash(self, plain: str) -> str:
        """Return an argon2id PHC string for ``plain``."""
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        """Return whether ``plain`` matches ``hashed``; never raises.

        A password check is a fail-closed predicate: any error (mismatch,
        malformed/garbage hash, wrong type, or an unexpected argon2 error) means
        "not a match", so a corrupted stored hash can never accidentally grant
        access.
        """
        try:
            return self._hasher.verify(hashed, plain)
        except Exception:
            return False


def build_password_hasher(settings: Settings) -> PasswordHasher:
    """Construct a :class:`PasswordHasher` from settings' argon2 parameters."""
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
    )
