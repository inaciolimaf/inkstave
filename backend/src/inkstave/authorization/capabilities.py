"""The role → capability matrix (spec 34) — the single source of truth.

Roles come from spec-33 memberships (`owner`/`editor`/`viewer`); a non-member is
represented as ``None``. The matrix below is authoritative; the authorization
service consults nothing else.

``capabilities_for`` is consumed both by the production project-scoped gate
(``authorization/dependencies.py::require_capability``) and by the spec-34 §5.2
``AuthorizationService`` facade (``authorization/service.py``); both delegate to
this single matrix so capability decisions cannot drift (issue #136).
"""

from __future__ import annotations

import enum

from inkstave.db.models.membership import MembershipRole


class Capability(enum.StrEnum):
    PROJECT_READ = "project_read"
    PROJECT_WRITE = "project_write"  # rename / settings
    PROJECT_DELETE = "project_delete"
    PROJECT_SHARE = "project_share"  # manage members / invites / transfer
    DOC_READ = "doc_read"
    DOC_WRITE = "doc_write"  # create/edit/move/delete docs + tree
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"  # upload/delete binary files
    COLLAB_READ = "collab_read"  # join the WS room, receive sync/awareness
    COLLAB_WRITE = "collab_write"  # send Yjs updates
    COMPILE = "compile"
    PROJECT_DOWNLOAD = "project_download"  # export the whole project as a .zip (spec 102)


# Editor: everything except project-level admin (write/delete/share).
_EDITOR: frozenset[Capability] = frozenset(
    {
        Capability.PROJECT_READ,
        Capability.DOC_READ,
        Capability.DOC_WRITE,
        Capability.FILE_READ,
        Capability.FILE_WRITE,
        Capability.COLLAB_READ,
        Capability.COLLAB_WRITE,
        Capability.COMPILE,
        Capability.PROJECT_DOWNLOAD,
    }
)

# Viewer: read-only everywhere; may compile (gated by COMPILE_ALLOWED_FOR_VIEWERS).
_VIEWER: frozenset[Capability] = frozenset(
    {
        Capability.PROJECT_READ,
        Capability.DOC_READ,
        Capability.FILE_READ,
        Capability.COLLAB_READ,
        Capability.COMPILE,
        Capability.PROJECT_DOWNLOAD,
    }
)


def capabilities_for(
    role: MembershipRole | None, *, compile_for_viewers: bool = True
) -> frozenset[Capability]:
    """The capability set for a role; empty for a non-member (``None``)."""
    if role == MembershipRole.owner:
        return frozenset(Capability)  # owner has every capability
    if role == MembershipRole.editor:
        return _EDITOR
    if role == MembershipRole.viewer:
        return _VIEWER if compile_for_viewers else _VIEWER - {Capability.COMPILE}
    return frozenset()  # non-member
