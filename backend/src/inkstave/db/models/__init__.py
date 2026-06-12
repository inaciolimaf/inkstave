"""Model registry.

Importing this package imports every model so that ``Base.metadata`` is fully
populated — Alembic autogenerate relies on this to see all tables.
"""

from inkstave.agent.diffs.models import ProposedDiff, ProposedDiffStatus
from inkstave.agent.models import (
    AgentMessage,
    AgentMessageRole,
    AgentRunState,
    AgentSession,
    AgentSessionStatus,
)
from inkstave.agent.safety.models import AgentAuditAction, AgentAuditLog
from inkstave.db.models.compile import Compile, CompileJobStatus
from inkstave.db.models.compile_output import CompileOutput, OutputKind
from inkstave.db.models.crdt import CrdtDocumentState, CrdtUpdate
from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.history import HistoryChunk, HistoryLabel, HistoryUpdate
from inkstave.db.models.invite import InviteRole, InviteStatus, ProjectInvite
from inkstave.db.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.db.models.notification import Notification, NotificationType
from inkstave.db.models.ping import Ping
from inkstave.db.models.project import Project
from inkstave.db.models.project_import import ProjectImport, ProjectImportStatus
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.db.models.user import User

__all__ = [
    "AgentAuditAction",
    "AgentAuditLog",
    "AgentMessage",
    "AgentMessageRole",
    "AgentRunState",
    "AgentSession",
    "AgentSessionStatus",
    "ProposedDiff",
    "ProposedDiffStatus",
    "Compile",
    "CompileJobStatus",
    "CompileOutput",
    "CrdtDocumentState",
    "CrdtUpdate",
    "OutputKind",
    "Document",
    "File",
    "HistoryChunk",
    "HistoryLabel",
    "HistoryUpdate",
    "InviteRole",
    "InviteStatus",
    "ProjectInvite",
    "MembershipRole",
    "MembershipStatus",
    "ProjectMembership",
    "Notification",
    "NotificationType",
    "Ping",
    "Project",
    "ProjectImport",
    "ProjectImportStatus",
    "TreeEntity",
    "TreeEntityType",
    "User",
]
