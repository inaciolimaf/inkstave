"""Projects: their tree, documents, files, members and who may do what with them."""

from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.file import File
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.modules.projects.models.invite import ProjectInvite
from inkstave.modules.projects.access.capabilities import Capability, capabilities_for
from inkstave.modules.projects.access.service import active_member_ids, role_for
from inkstave.modules.projects.catalog.service import ProjectNotFoundError, create_project
from inkstave.modules.projects.tree.safe_path import InvalidNameError, validate_name_segment
from inkstave.modules.projects.tree.service import (
    EntityNotFoundError,
    ParentNotAFolderError,
    compute_path,
    create_entity,
    delete_entity,
    get_entity,
    get_tree,
    move_entity,
    rename_entity,
)
from inkstave.modules.projects.content.files import BlobMissingError, open_file_content
from inkstave.modules.projects.content.documents import (
    NotADocumentError,
    get_document,
    read_content_for_collab,
    set_content_from_collab,
)
from inkstave.modules.projects.access.deps import require_capability

__all__ = [
    "BlobMissingError",
    "Capability",
    "Document",
    "EntityNotFoundError",
    "File",
    "InvalidNameError",
    "NotADocumentError",
    "ParentNotAFolderError",
    "Project",
    "ProjectInvite",
    "ProjectNotFoundError",
    "TreeEntity",
    "TreeEntityType",
    "active_member_ids",
    "capabilities_for",
    "compute_path",
    "create_entity",
    "create_project",
    "delete_entity",
    "get_document",
    "get_entity",
    "get_tree",
    "move_entity",
    "open_file_content",
    "read_content_for_collab",
    "rename_entity",
    "require_capability",
    "role_for",
    "set_content_from_collab",
    "validate_name_segment",
]
