"""Model registry.

Importing this package imports every model so that ``Base.metadata`` is fully
populated — Alembic autogenerate relies on this to see all tables.
"""

from inkstave.db.models.compile import Compile, CompileJobStatus
from inkstave.db.models.compile_output import CompileOutput, OutputKind
from inkstave.db.models.document import Document
from inkstave.db.models.file import File
from inkstave.db.models.ping import Ping
from inkstave.db.models.project import Project
from inkstave.db.models.tree_entity import TreeEntity, TreeEntityType
from inkstave.db.models.user import User

__all__ = [
    "Compile",
    "CompileJobStatus",
    "CompileOutput",
    "OutputKind",
    "Document",
    "File",
    "Ping",
    "Project",
    "TreeEntity",
    "TreeEntityType",
    "User",
]
