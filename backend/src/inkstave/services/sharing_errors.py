"""Domain errors for the collaborators & sharing service (spec 33).

These are typed domain errors mapped to HTTP codes by the error layer. They are
re-exported from :mod:`inkstave.services.sharing`.
"""

from __future__ import annotations

from inkstave.errors import BadRequestError, ConflictError, ForbiddenError, GoneError, NotFoundError


class NotProjectOwnerError(ForbiddenError):
    error_type = "not_project_owner"

    def __init__(self) -> None:
        super().__init__("Only the project owner can perform this action.")


class MemberNotFoundError(NotFoundError):
    error_type = "member_not_found"

    def __init__(self) -> None:
        super().__init__("Member not found.")


class AlreadyMemberError(ConflictError):
    error_type = "already_member"

    def __init__(self) -> None:
        super().__init__("That person is already a member of this project.")


class OwnerCannotLeaveError(BadRequestError):
    error_type = "owner_cannot_leave"

    def __init__(self) -> None:
        super().__init__("Transfer ownership before leaving the project.")


class CannotChangeOwnerRoleError(BadRequestError):
    error_type = "cannot_change_owner_role"

    def __init__(self) -> None:
        super().__init__("The owner's role can only change via ownership transfer.")


class NotAMemberError(BadRequestError):
    error_type = "not_a_member"

    def __init__(self) -> None:
        super().__init__("Ownership can only be transferred to an active member.")


class InvalidRoleError(BadRequestError):
    error_type = "invalid_role"

    def __init__(self) -> None:
        super().__init__("Role must be 'editor' or 'viewer'.")


class InviteNotFoundError(NotFoundError):
    error_type = "invite_not_found"

    def __init__(self) -> None:
        super().__init__("Invite not found.")


class InviteGoneError(GoneError):
    error_type = "invite_gone"

    def __init__(self) -> None:
        super().__init__("This invite is no longer valid.")


class InviteEmailMismatchError(ForbiddenError):
    error_type = "invite_email_mismatch"

    def __init__(self) -> None:
        super().__init__("This invite was addressed to a different email.")
