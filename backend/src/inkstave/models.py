"""Model registry.

Importing this package imports every model so that ``Base.metadata`` is fully
populated — Alembic autogenerate relies on this to see all tables.
"""

from inkstave.modules.admin.models import Ping
from inkstave.modules.agent.diffs.models import ProposedDiff, ProposedDiffStatus
from inkstave.modules.agent.file_ops.models import ProposedFileOp, ProposedFileOpStatus
from inkstave.modules.agent.models import (
    AgentMessage,
    AgentMessageRole,
    AgentRunState,
    AgentSession,
    AgentSessionStatus,
)
from inkstave.modules.agent.safety.models import AgentAuditAction, AgentAuditLog
from inkstave.modules.auth.models.auth_token import AuthToken
from inkstave.modules.auth.models.revoked_session import RevokedSession
from inkstave.modules.auth.models.user import User
from inkstave.modules.auth.models.user_dictionary_word import user_dictionary_words
from inkstave.modules.collab.models import CrdtDocumentState, CrdtUpdate
from inkstave.modules.compile.models.compile import Compile, CompileJobStatus
from inkstave.modules.compile.models.compile_output import CompileOutput, OutputKind
from inkstave.modules.discussion.models import ProjectChatMessage, ProjectChatRead
from inkstave.modules.history.models import HistoryChunk, HistoryLabel, HistoryUpdate
from inkstave.modules.notifications.models import Notification, NotificationType
from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.file import File
from inkstave.modules.projects.models.invite import InviteRole, InviteStatus, ProjectInvite
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.project_import import ProjectImport, ProjectImportStatus
from inkstave.modules.projects.models.share_link import ProjectShareLink, ShareLinkRole
from inkstave.modules.projects.models.tree_entity import TreeEntity, TreeEntityType

__all__ = [
    "AgentAuditAction",
    "AgentAuditLog",
    "AgentMessage",
    "AgentMessageRole",
    "AgentRunState",
    "AgentSession",
    "AgentSessionStatus",
    "AuthToken",
    "Compile",
    "CompileJobStatus",
    "CompileOutput",
    "CrdtDocumentState",
    "CrdtUpdate",
    "Document",
    "File",
    "HistoryChunk",
    "HistoryLabel",
    "HistoryUpdate",
    "InviteRole",
    "InviteStatus",
    "MembershipRole",
    "MembershipStatus",
    "Notification",
    "NotificationType",
    "OutputKind",
    "Ping",
    "Project",
    "ProjectChatMessage",
    "ProjectChatRead",
    "ProjectImport",
    "ProjectImportStatus",
    "ProjectInvite",
    "ProjectMembership",
    "ProjectShareLink",
    "ProposedDiff",
    "ProposedDiffStatus",
    "ProposedFileOp",
    "ProposedFileOpStatus",
    "RevokedSession",
    "ShareLinkRole",
    "TreeEntity",
    "TreeEntityType",
    "User",
    "user_dictionary_words",
]
