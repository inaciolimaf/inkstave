"""The versioned ``/api/v1`` router.

Feature routers (auth, projects, documents, …) are attached here by later
specs. For now it exists as the stable mount point under which the OpenAPI
schema and all versioned endpoints live.
"""

from __future__ import annotations

from fastapi import APIRouter

from inkstave.agent.api import routes as agent_routes
from inkstave.api.routes import (
    admin,
    auth,
    compile,
    documents,
    files,
    history,
    notifications,
    projects,
    sharing,
    tree,
    users,
)
from inkstave.logparse import router as logparse
from inkstave.synctex import router as synctex

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(users.router)
api_v1.include_router(admin.router)
api_v1.include_router(projects.router)
api_v1.include_router(sharing.router)
api_v1.include_router(sharing.invites_router)
api_v1.include_router(tree.router)
api_v1.include_router(documents.router)
api_v1.include_router(files.router)
api_v1.include_router(compile.router)
api_v1.include_router(synctex.router)
api_v1.include_router(logparse.router)
api_v1.include_router(history.router)
api_v1.include_router(notifications.router)
api_v1.include_router(agent_routes.router)
