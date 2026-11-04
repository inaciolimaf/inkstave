"""The user's decision on a proposed diff, hunk by hunk (spec 110)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.agent.diffs import repository as diff_repo
from inkstave.modules.agent.diffs.models import ProposedDiff
from inkstave.modules.agent.diffs.repository import NewDiff
from inkstave.modules.agent.diffs.schemas import DiffOutcomeIn
from inkstave.modules.agent.safety.models import AgentAuditAction, AgentAuditLog
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.catalog.service import create_project
from inkstave.modules.projects.models.membership import MembershipRole
from tests.factories import UserFactory
from tests.integration._agent_api_support import API, _make_session, seed
from tests.integration._agent_tools_support import _member

pytestmark = pytest.mark.integration

__all__ = ["seed"]


def bearer(user: Any) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _hunk(hunk_id: str) -> dict[str, Any]:
    return {
        "hunk_id": hunk_id,
        "header": "@@ -1 +1 @@",
        "old_start": 1,
        "old_lines": 1,
        "new_start": 1,
        "new_lines": 1,
        "lines": [{"op": "-", "text": "old"}, {"op": "+", "text": "new"}],
        "additions": 1,
        "deletions": 1,
    }


async def _diff(db: AsyncSession, seed: SimpleNamespace, session: Any, hunk_ids: list[str]) -> ProposedDiff:
    row = await diff_repo.create(
        db,
        NewDiff(
            session_id=session.id,
            message_id=None,
            project_id=seed.project.id,
            doc_id=seed.main_id,
            path="main.tex",
            base_version="0",
            base_hash="hash",
            diff_text="",
            hunks=[_hunk(h) for h in hunk_ids],
            stats={"additions": len(hunk_ids), "deletions": len(hunk_ids), "hunk_count": len(hunk_ids)},
        ),
    )
    await db.commit()
    await db.refresh(row)  # the commit expired the row; reading its id later must not do IO
    return row


def _url(seed: SimpleNamespace, session: Any, diff: ProposedDiff) -> str:
    return f"{API}/{seed.project.id}/agent/sessions/{session.id}/diffs/{diff.id}/outcome"


async def test_outcome_is_stored_and_listed(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient
) -> None:
    session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1", "h2", "h3"])
    body = {"accepted": ["h1", "h3"], "rejected": ["h2"], "stale": []}

    response = await async_client.post(_url(seed, session, diff), json=body, headers=seed.headers)
    assert response.status_code == 200
    assert response.json()["status"] == "partially_applied"

    stored = await db_session.get(ProposedDiff, diff.id, populate_existing=True)
    assert stored is not None and stored.decided_by == seed.owner.id and stored.decided_at is not None
    assert stored.decided_hunks == {"accepted": ["h1", "h3"], "rejected": ["h2"], "stale": []}

    detail = await async_client.get(
        f"{API}/{seed.project.id}/agent/sessions/{session.id}", headers=seed.headers
    )
    listed = {d["id"]: d for d in detail.json()["diffs"]}
    assert listed[str(diff.id)]["status"] == "partially_applied"

    audit = await db_session.execute(
        select(AgentAuditLog).where(AgentAuditLog.action == AgentAuditAction.proposal_decided.value)
    )
    assert [row.detail["diff_id"] for row in audit.scalars()] == [str(diff.id)]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"accepted": ["h1", "h2"], "rejected": [], "stale": []}, "applied"),
        ({"accepted": [], "rejected": ["h1"], "stale": ["h2"]}, "stale"),
        ({"accepted": [], "rejected": ["h1", "h2"], "stale": []}, "rejected"),
        ({"accepted": ["h1"], "rejected": [], "stale": ["h2"]}, "partially_applied"),
    ],
)
async def test_status_follows_the_hunk_counts(
    seed: SimpleNamespace,
    db_session: AsyncSession,
    async_client: AsyncClient,
    body: dict[str, list[str]],
    expected: str,
) -> None:
    session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1", "h2"])
    response = await async_client.post(_url(seed, session, diff), json=body, headers=seed.headers)
    assert response.status_code == 200 and response.json()["status"] == expected


async def test_outcome_conflict_409(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient
) -> None:
    session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1"])
    url = _url(seed, session, diff)
    await async_client.post(url, json={"accepted": ["h1"]}, headers=seed.headers)

    again = await async_client.post(url, json={"rejected": ["h1"]}, headers=seed.headers)
    assert again.status_code == 409
    error = again.json()["error"]
    assert error["type"] == "already_decided" and error["details"] == [{"status": "applied"}]


@pytest.mark.parametrize(
    "body",
    [
        {"accepted": ["h1"]},  # h2 is missing
        {"accepted": ["h1", "h2", "h9"]},  # unknown id
        {"accepted": ["h1", "h2"], "rejected": ["h2"]},  # listed twice
    ],
)
async def test_outcome_must_list_every_hunk_once(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient, body: dict[str, list[str]]
) -> None:
    session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1", "h2"])
    response = await async_client.post(_url(seed, session, diff), json=body, headers=seed.headers)
    assert response.status_code == 422 and response.json()["error"]["type"] == "invalid_outcome"


async def test_outcome_is_not_found_across_sessions_and_projects(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient
) -> None:
    owner_id = seed.owner.id
    project_id = seed.project.id
    session = await _make_session(db_session, seed)
    other_session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1"])
    session_id, other_id, diff_id = session.id, other_session.id, diff.id
    body = {"accepted": ["h1"]}

    wrong_session = f"{API}/{project_id}/agent/sessions/{other_id}/diffs/{diff_id}/outcome"
    response = await async_client.post(wrong_session, json=body, headers=seed.headers)
    assert response.status_code == 404 and response.json()["error"]["type"] == "diff_not_found"

    elsewhere = await create_project(db_session, owner_id, "Other")
    elsewhere_id = elsewhere.id
    await db_session.commit()
    wrong_project = f"{API}/{elsewhere_id}/agent/sessions/{session_id}/diffs/{diff_id}/outcome"
    response = await async_client.post(wrong_project, json=body, headers=seed.headers)
    assert response.status_code == 404 and response.json()["error"]["type"] == "project_not_found"
    stored = await db_session.get(ProposedDiff, diff_id, populate_existing=True)
    assert stored is not None and stored.status == "proposed"


async def test_a_viewer_cannot_record_an_outcome(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient
) -> None:
    session = await _make_session(db_session, seed)
    diff = await _diff(db_session, seed, session, ["h1"])
    url, diff_id = _url(seed, session, diff), diff.id
    viewer = await UserFactory.create(db_session)
    await _member(db_session, seed.project.id, viewer.id, MembershipRole.viewer)
    session.user_id = viewer.id
    headers = bearer(viewer)
    await db_session.commit()

    response = await async_client.post(url, json={"accepted": ["h1"]}, headers=headers)
    assert response.status_code == 403 and response.json()["error"]["type"] == "diff_forbidden"
    stored = await db_session.get(ProposedDiff, diff_id, populate_existing=True)
    assert stored is not None and stored.status == "proposed"


async def test_listing_draws_hunks_only_when_asked(
    seed: SimpleNamespace, db_session: AsyncSession, async_client: AsyncClient
) -> None:
    session = await _make_session(db_session, seed)
    await _diff(db_session, seed, session, ["h1"])
    base = f"{API}/{seed.project.id}/agent/sessions/{session.id}/diffs"

    plain = (await async_client.get(base, headers=seed.headers)).json()
    assert plain[0]["hunks"] is None
    with_hunks = (await async_client.get(f"{base}?include=hunks", headers=seed.headers)).json()
    assert [h["hunk_id"] for h in with_hunks[0]["hunks"]] == ["h1"]


def test_outcome_body_defaults_to_empty_lists() -> None:
    body = DiffOutcomeIn()
    assert body.accepted == [] and body.rejected == [] and body.stale == []
