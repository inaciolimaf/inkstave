"""Collaborators & sharing service (spec 33).

The single source of truth for *who can access a project and as what*. Membership
roles are stored here; the consistent capability guard across REST/WS/compile is
spec 34. These functions are transaction-bounded (the ``get_db_session``
dependency commits) and raise typed domain errors mapped to HTTP codes.

Access policy mirrors the project service (ADR 0007): a user who is not a member
of a project sees ``404`` (existence is not leaked); a member who is not the owner
gets ``403`` on owner-only operations.

This module is the public surface; the implementation is split across sibling
modules (``sharing_errors``, ``sharing_common``, ``sharing_members``,
``sharing_invites``) for readability. Import from here.
"""

from __future__ import annotations

from inkstave.services.sharing_common import (
    MemberInfo,
    generate_token,
    hash_token,
    membership_of,
    require_member,
    require_owner,
)
from inkstave.services.sharing_errors import (
    AlreadyMemberError,
    CannotChangeOwnerRoleError,
    InvalidRoleError,
    InviteEmailMismatchError,
    InviteGoneError,
    InviteNotFoundError,
    MemberNotFoundError,
    NotAMemberError,
    NotProjectOwnerError,
    OwnerCannotLeaveError,
)
from inkstave.services.sharing_invites import (
    accept_invite,
    create_invite,
    decline_invite,
    get_invite_preview,
    list_invites,
    revoke_invite,
)
from inkstave.services.sharing_members import (
    change_role,
    list_members,
    remove_member,
    transfer_ownership,
)

__all__ = [
    # errors
    "AlreadyMemberError",
    "CannotChangeOwnerRoleError",
    "InvalidRoleError",
    "InviteEmailMismatchError",
    "InviteGoneError",
    "InviteNotFoundError",
    "MemberNotFoundError",
    "NotAMemberError",
    "NotProjectOwnerError",
    "OwnerCannotLeaveError",
    # value objects
    "MemberInfo",
    # token helpers & guards
    "generate_token",
    "hash_token",
    "membership_of",
    "require_member",
    "require_owner",
    # members
    "change_role",
    "list_members",
    "remove_member",
    "transfer_ownership",
    # invites
    "accept_invite",
    "create_invite",
    "decline_invite",
    "get_invite_preview",
    "list_invites",
    "revoke_invite",
]
