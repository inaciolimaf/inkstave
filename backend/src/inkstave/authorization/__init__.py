"""Centralized authorization: role→capability matrix + service + dependency (spec 34)."""

from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.authorization.service import InsufficientRoleError, role_for

__all__ = [
    "Capability",
    "InsufficientRoleError",
    "capabilities_for",
    "role_for",
]
