"""Error types for the file-tree service (spec 12).

Split out from :mod:`inkstave.services.tree_service` for file-size hygiene; the
service module re-exports these so existing import paths keep working.
"""

from __future__ import annotations

from inkstave.errors import AppError, ConflictError, NotFoundError


class EntityNotFoundError(NotFoundError):
    error_type = "entity_not_found"

    def __init__(self) -> None:
        super().__init__("Tree entity not found.")


class ParentNotFoundError(NotFoundError):
    error_type = "parent_not_found"

    def __init__(self) -> None:
        super().__init__("Parent folder not found.")


class ParentNotAFolderError(AppError):
    status_code = 422
    error_type = "parent_not_a_folder"

    def __init__(self) -> None:
        super().__init__("Parent must be a folder.")


class NameConflictError(ConflictError):
    error_type = "name_conflict"

    def __init__(self) -> None:
        super().__init__("An entity with this name already exists in the folder.")


class TreeCycleError(ConflictError):
    error_type = "tree_cycle"

    def __init__(self) -> None:
        super().__init__("Cannot move a folder into itself or a descendant.")


class RootImmutableError(ConflictError):
    error_type = "root_immutable"

    def __init__(self) -> None:
        super().__init__("The project root cannot be modified.")
