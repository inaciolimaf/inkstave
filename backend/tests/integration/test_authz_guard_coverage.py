"""Spec-35 audit: every project-scoped REST route carries an authorization guard.

This fails the moment a new ``{project_id}`` route is added without either the
central ``require_capability`` dependency or an explicit, documented in-handler
guard — closing the "permission hole" class for good (spec 34 AC + spec 35 AC3).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute

from inkstave.app import create_app

pytestmark = pytest.mark.integration

# Routes whose authorization is enforced *inside* the handler/service rather than
# via the ``require_capability`` dependency. Each is audited here by hand:
#   - sharing routes call the sharing service's require_member/require_owner;
#   - /permissions and the SSE /events route call authz.role_for directly
#     (custom auth: SSE uses a query-param token, /permissions returns role+caps);
#   - the agent routes (spec 44) call `_require_member` in-handler, which is 404 for
#     an unknown project and 403 for a non-member (a deliberately different contract
#     from require_capability's 404-for-non-member), and SSE uses a query-param token.
_AGENT = "/api/v1/projects/{project_id}/agent"
_HANDLER_GUARDED: frozenset[str] = frozenset(
    {
        "/api/v1/projects/{project_id}/members",
        "/api/v1/projects/{project_id}/members/{user_id}",
        "/api/v1/projects/{project_id}/members/transfer",
        "/api/v1/projects/{project_id}/invites",
        "/api/v1/projects/{project_id}/invites/{invite_id}",
        "/api/v1/projects/{project_id}/permissions",
        "/api/v1/projects/{project_id}/compile/{compile_id}/events",
        # The import SSE /events route uses a query-param token (spec 101), like compile.
        "/api/v1/projects/{project_id}/import/{import_id}/events",
        f"{_AGENT}/sessions",
        f"{_AGENT}/sessions/{{session_id}}",
        f"{_AGENT}/sessions/{{session_id}}/messages",
        f"{_AGENT}/sessions/{{session_id}}/runs/{{run_id}}/events",
        f"{_AGENT}/sessions/{{session_id}}/runs/{{run_id}}/cancel",
        f"{_AGENT}/sessions/{{session_id}}/diffs",
    }
)


def _calls(dependant: Any) -> Iterator[Any]:
    yield dependant.call
    for sub in dependant.dependencies:
        yield from _calls(sub)


def _has_capability_guard(route: APIRoute) -> bool:
    return any(
        getattr(c, "__authz_capability__", None) is not None for c in _calls(route.dependant)
    )


def test_every_project_scoped_route_is_guarded() -> None:
    app = create_app()
    project_routes = [r for r in app.routes if isinstance(r, APIRoute) and "{project_id}" in r.path]
    # Sanity: the audit actually covers the surface, not an empty set.
    assert len(project_routes) >= 15, len(project_routes)

    unguarded: list[tuple[list[str], str]] = []
    for route in project_routes:
        if route.path in _HANDLER_GUARDED:
            continue
        if not _has_capability_guard(route):
            unguarded.append((sorted(route.methods or []), route.path))

    assert unguarded == [], f"unguarded project-scoped routes: {unguarded}"


def test_handler_guarded_allowlist_routes_exist() -> None:
    """The allowlist must not rot: every entry maps to a real route."""
    app = create_app()
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    missing = _HANDLER_GUARDED - paths
    assert missing == set(), f"allowlist references non-existent routes: {missing}"
