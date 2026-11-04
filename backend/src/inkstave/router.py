"""The versioned ``/api/v1`` router.

Feature routers (auth, projects, documents, …) are attached here by later
specs. For now it exists as the stable mount point under which the OpenAPI
schema and all versioned endpoints live.
"""

from __future__ import annotations

from fastapi import APIRouter

from inkstave.modules.admin.routes import admin, public_config
from inkstave.modules.agent import routes as agent_routes
from inkstave.modules.agent.file_ops import routes as agent_file_op_routes
from inkstave.modules.auth.routes import auth, dictionary, users
from inkstave.modules.compile.routes import compile as compile_routes
from inkstave.modules.compile.routes import logparse, synctex
from inkstave.modules.discussion.routes import chat as chat_routes
from inkstave.modules.discussion.routes import comments as comment_thread_routes
from inkstave.modules.discussion.routes import events as event_routes
from inkstave.modules.git.routes import smart_http as git_smart_http
from inkstave.modules.git.routes import tokens as git_tokens
from inkstave.modules.history import routes as history
from inkstave.modules.notifications import routes as notifications
from inkstave.modules.projects.routes import (
    documents,
    files,
    project_import,
    projects,
    share_links,
    sharing,
    tree,
)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(users.router)
api_v1.include_router(dictionary.router)
api_v1.include_router(admin.router)
api_v1.include_router(public_config.router)
api_v1.include_router(git_tokens.router)
api_v1.include_router(git_smart_http.router)
api_v1.include_router(projects.router)
api_v1.include_router(project_import.router)
api_v1.include_router(sharing.router)
api_v1.include_router(sharing.invites_router)
api_v1.include_router(share_links.router)
api_v1.include_router(share_links.links_router)
api_v1.include_router(tree.router)
api_v1.include_router(documents.router)
api_v1.include_router(files.router)
api_v1.include_router(compile_routes.router)
api_v1.include_router(synctex.router)
api_v1.include_router(logparse.router)
api_v1.include_router(chat_routes.router)
api_v1.include_router(comment_thread_routes.router)
api_v1.include_router(event_routes.router)
api_v1.include_router(history.router)
api_v1.include_router(notifications.router)
api_v1.include_router(agent_routes.router)
api_v1.include_router(agent_file_op_routes.router)
