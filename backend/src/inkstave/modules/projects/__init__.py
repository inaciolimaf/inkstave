"""Projects: their tree, documents, files, members and who may do what with them."""

from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.file import File
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.modules.projects.models.invite import ProjectInvite
from inkstave.modules.projects.access.capabilities import Capability, capabilities_for
from inkstave.modules.projects.access.service import role_for
from inkstave.modules.projects.catalog.service import ProjectNotFoundError, create_project
from inkstave.modules.projects.tree.service import (
    EntityNotFoundError,
    compute_path,
    create_entity,
    get_entity,
    get_tree,
)
from inkstave.modules.projects.content.documents import (
    NotADocumentError,
    get_document,
    read_content_for_collab,
    set_content_from_collab,
)
from inkstave.modules.projects.access.deps import require_capability

__all__ = [
    "Capability",
    "Document",
    "EntityNotFoundError",
    "File",
    "NotADocumentError",
    "Project",
    "ProjectInvite",
    "ProjectNotFoundError",
    "TreeEntity",
    "TreeEntityType",
    "capabilities_for",
    "compute_path",
    "create_entity",
    "create_project",
    "get_document",
    "get_entity",
    "get_tree",
    "read_content_for_collab",
    "require_capability",
    "role_for",
    "set_content_from_collab",
]
