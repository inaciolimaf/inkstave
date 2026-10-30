"""Centralized authorization: role→capability matrix + service + dependency (spec 34)."""

from inkstave.modules.projects.access.capabilities import Capability, capabilities_for
from inkstave.modules.projects.access.service import InsufficientRoleError, role_for

__all__ = [
    "Capability",
    "InsufficientRoleError",
    "capabilities_for",
    "role_for",
]
