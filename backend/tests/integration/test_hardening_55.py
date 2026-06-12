"""Spec-55 hardening regressions: one test per applied fix.

Each test fails against the pre-spec-55 code and passes after the fix. Security
and flakiness fixes get a dedicated regression here (spec 55 AC 2-5).
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from inkstave.app import create_app
from inkstave.auth.rate_limit import rate_limit
from inkstave.config import Settings
from inkstave.observability.context import request_id_var
from inkstave.observability.log import redact

pytestmark = pytest.mark.integration


# --- Spec 51: redaction denylist closes the S3 access-key gap ----------------- #


def test_secret_access_key_is_redacted() -> None:
    # s3_access_key_id contains "access_key_id" — it did NOT match the old denylist
    # ("api_key"), so it would have leaked. Spec 55 added "access_key".
    out = redact({"s3_access_key_id": "AKIAEXAMPLE", "user_id": "u1", "count": 3})
    assert out["s3_access_key_id"] == "***REDACTED***"
    assert out["user_id"] == "u1" and out["count"] == 3  # benign fields untouched


# --- Spec 51: the agent job binds + always clears correlation context --------- #


async def test_agent_job_binds_and_clears_context(monkeypatch: pytest.MonkeyPatch) -> None:
    from inkstave.agent.api import jobs

    seen: dict[str, Any] = {}

    async def fake_inner(ctx: Any, *, session_id: str, run_id: str, user_message: str) -> None:
        seen["request_id"] = request_id_var.get()

    monkeypatch.setattr(jobs, "_run_agent_turn", fake_inner)

    token = request_id_var.set("outer")
    try:
        await jobs.run_agent_turn(
            {}, session_id="s", run_id="r", user_message="m", request_id="req-123"
        )
        assert seen["request_id"] == "req-123"  # request id chained into the job
        assert request_id_var.get() == "outer"  # restored after — no leak to next job
    finally:
        request_id_var.reset(token)


# --- Spec 52: auth limiter sets the TTL atomically (no key without expiry) ----- #


async def test_auth_limiter_sets_ttl_on_first_hit(redis: Any) -> None:
    settings = Settings(_env_file=None, rate_limit_refresh="5/60")  # type: ignore[call-arg]
    dep = rate_limit("refresh")
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4"))
    await dep(req, redis, settings)
    ttl = await redis.ttl("ratelimit:refresh:1.2.3.4")
    assert ttl > 0, "INCR+EXPIRE must be atomic so a counter is never left un-expiring"


# --- Spec 52: every sensitive route carries a rate-limit policy ---------------- #

_AGENT = "/api/v1/projects/{project_id}/agent"
_SENSITIVE: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/projects/{project_id}/compile"),
        ("POST", "/api/v1/projects/{project_id}/files"),
        ("POST", f"{_AGENT}/sessions/{{session_id}}/messages"),
        # spec 68 #217: change-password is a sensitive auth endpoint (5/hour).
        ("POST", "/api/v1/users/me/change-password"),
    }
)


def _calls(dependant: Any) -> Iterator[Any]:
    yield dependant.call
    for sub in dependant.dependencies:
        yield from _calls(sub)


def _has_rate_limit(route: APIRoute) -> bool:
    return any(getattr(c, "__rate_limit__", None) is not None for c in _calls(route.dependant))


def test_every_sensitive_route_is_rate_limited() -> None:
    app = create_app()
    by_key = {
        (method, r.path): r
        for r in app.routes
        if isinstance(r, APIRoute)
        for method in (r.methods or set())
    }
    missing: list[tuple[str, str]] = []
    for key in _SENSITIVE:
        route = by_key.get(key)
        assert route is not None, f"sensitive route not found: {key}"
        if not _has_rate_limit(route):
            missing.append(key)
    assert missing == [], f"sensitive routes without a rate-limit policy: {missing}"


# --- Spec 52: secure headers on error/404 responses; extra fields rejected ----- #


async def test_security_headers_present_on_error_responses(async_client: AsyncClient) -> None:
    # 404 for an unknown path still carries the secure headers.
    res = await async_client.get("/api/v1/this-route-does-not-exist")
    assert res.status_code == 404
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"

    # A 422 validation error also carries them.
    bad = await async_client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert bad.status_code == 422
    assert bad.headers.get("x-content-type-options") == "nosniff"


async def test_unknown_request_field_is_rejected(async_client: AsyncClient) -> None:
    # extra="forbid" (StrictModel) now closes request smuggling on a bare request model.
    res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "secret123", "is_admin": True},
    )
    assert res.status_code == 422


def test_request_models_forbid_extra_fields() -> None:
    from inkstave.agent.api.schemas import CreateSessionIn, PostMessageIn
    from inkstave.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest
    from inkstave.schemas.compile import CompileRequest
    from inkstave.schemas.document import DocumentContentReplace
    from inkstave.schemas.history import (
        LabelCreate,
        ProjectLabelCreate,
        ProjectRestoreRequest,
        RestoreRequest,
    )
    from inkstave.schemas.project import ProjectCreate, ProjectRename
    from inkstave.schemas.sharing import InviteCreate, MemberRoleUpdate, TransferRequest
    from inkstave.schemas.tree import CreateEntityIn, MoveEntityIn, RenameEntityIn
    from inkstave.schemas.user import RegisterRequest

    request_models = [
        LoginRequest,
        RefreshRequest,
        LogoutRequest,
        RegisterRequest,
        ProjectCreate,
        ProjectRename,  # spec 68 #28
        DocumentContentReplace,  # spec 68 #218
        CreateEntityIn,
        RenameEntityIn,
        MoveEntityIn,
        MemberRoleUpdate,
        TransferRequest,
        InviteCreate,
        CompileRequest,
        LabelCreate,
        ProjectLabelCreate,
        RestoreRequest,
        ProjectRestoreRequest,
        PostMessageIn,
        CreateSessionIn,
    ]
    offenders = [m.__name__ for m in request_models if m.model_config.get("extra") != "forbid"]
    assert offenders == [], f"request models missing extra='forbid': {offenders}"
