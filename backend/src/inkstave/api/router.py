"""The versioned ``/api/v1`` router.

Feature routers (auth, projects, documents, …) are attached here by later
specs. For now it exists as the stable mount point under which the OpenAPI
schema and all versioned endpoints live.
"""

from __future__ import annotations

from fastapi import APIRouter

from inkstave.api.routes import (
    admin,
    auth,
    compile,
    documents,
    files,
    projects,
    tree,
    users,
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(users.router)
api_v1.include_router(admin.router)
api_v1.include_router(projects.router)
api_v1.include_router(tree.router)
api_v1.include_router(documents.router)
api_v1.include_router(files.router)
api_v1.include_router(compile.router)
