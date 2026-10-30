"""Unit tests for the sharing service + schema invariants (spec 33)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.invite import InviteStatus, ProjectInvite
from inkstave.db.models.membership import (
    MembershipRole,
    MembershipStatus,
    ProjectMembership,
)
from inkstave.schemas.sharing import InviteCreate
from inkstave.services import sharing
from inkstave.services.project import create_project
from tests.factories import UserFactory

pytestmark = pytest.mark.integration  # touches the DB


async def _owner_and_project(db_session: AsyncSession):
    owner = await UserFactory.create(db_session)
    await db_session.flush()
    project = await create_project(db_session, owner.id, "P")
    return owner, project


def test_token_generation_is_unique_and_high_entropy() -> None:
    tokens = {sharing.generate_token() for _ in range(200)}
    assert len(tokens) == 200  # no collisions
    assert all(len(t) >= 40 for t in tokens)  # ~32 bytes urlsafe


def test_hash_token_is_deterministic() -> None:
    assert sharing.hash_token("abc") == sharing.hash_token("abc")
    assert sharing.hash_token("abc") != sharing.hash_token("abd")


def test_invite_schema_rejects_owner_role() -> None:
    with pytest.raises(ValidationError):
        InviteCreate(email="x@example.com", role="owner")


async def test_create_invite_refreshes_existing_pending(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    inv1, tok1 = await sharing.create_invite(
        db_session, project.id, owner.id, "bob@example.com", "editor", ttl_days=14
    )
    inv2, tok2 = await sharing.create_invite(
        db_session, project.id, owner.id, "BOB@example.com", "viewer", ttl_days=14
    )
    assert inv1.id == inv2.id  # same row refreshed
    assert inv2.role == "viewer"
    assert tok1 != tok2  # a fresh token each time
    pending = (
        await db_session.execute(
            select(func.count())
            .select_from(ProjectInvite)
            .where(
                ProjectInvite.project_id == project.id,
                ProjectInvite.status == InviteStatus.pending,
            )
        )
    ).scalar_one()
    assert pending == 1


async def test_accept_requires_matching_email(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    _, raw = await sharing.create_invite(
        db_session, project.id, owner.id, "bob@example.com", "editor", ttl_days=14
    )
    carol = await UserFactory.create(db_session, email="carol@example.com")
    await db_session.flush()
    with pytest.raises(sharing.InviteEmailMismatchError):
        await sharing.accept_invite(db_session, raw, carol)


async def test_accept_is_case_insensitive_on_email(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    _, raw = await sharing.create_invite(
        db_session, project.id, owner.id, "Bob@Example.com", "viewer", ttl_days=14
    )
    bob = await UserFactory.create(db_session, email="bob@example.com")
    await db_session.flush()
    project_id, role = await sharing.accept_invite(db_session, raw, bob)
    assert project_id == project.id and role == "viewer"


async def test_transfer_demotes_previous_owner_to_editor(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    member = await UserFactory.create(db_session, email="m@example.com")
    await db_session.flush()
    db_session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=member.id,
            role=MembershipRole.editor,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()

    await sharing.transfer_ownership(db_session, project.id, owner.id, member.id)

    roles = {
        m.user_id: m.role
        for m in (
            await db_session.execute(
                select(ProjectMembership).where(ProjectMembership.project_id == project.id)
            )
        ).scalars()
    }
    assert roles[member.id] == MembershipRole.owner
    assert roles[owner.id] == MembershipRole.editor  # documented demotion target
    owners = [r for r in roles.values() if r == MembershipRole.owner]
    assert len(owners) == 1  # single-owner invariant


async def test_transfer_to_non_member_rejected(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    stranger = await UserFactory.create(db_session, email="s@example.com")
    await db_session.flush()
    with pytest.raises(sharing.NotAMemberError):
        await sharing.transfer_ownership(db_session, project.id, owner.id, stranger.id)


async def test_create_invite_sets_expiry_from_ttl(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    ttl_days = 7
    before = datetime.now(UTC)
    invite, _ = await sharing.create_invite(
        db_session, project.id, owner.id, "bob@example.com", "editor", ttl_days=ttl_days
    )
    after = datetime.now(UTC)
    # expires_at ≈ now() + timedelta(days=ttl_days); allow a small clock window.
    assert before + timedelta(days=ttl_days) - timedelta(seconds=5) <= invite.expires_at
    assert invite.expires_at <= after + timedelta(days=ttl_days) + timedelta(seconds=5)


async def test_change_role_transitions_and_rejects_owner(db_session: AsyncSession) -> None:
    owner, project = await _owner_and_project(db_session)
    member = await UserFactory.create(db_session, email="m@example.com")
    await db_session.flush()
    db_session.add(
        ProjectMembership(
            project_id=project.id,
            user_id=member.id,
            role=MembershipRole.editor,
            status=MembershipStatus.active,
        )
    )
    await db_session.flush()

    # editor -> viewer succeeds.
    info = await sharing.change_role(db_session, project.id, owner.id, member.id, "viewer")
    assert info.role == MembershipRole.viewer

    # viewer -> editor succeeds (round-trip).
    info = await sharing.change_role(db_session, project.id, owner.id, member.id, "editor")
    assert info.role == MembershipRole.editor

    # Promoting to owner via change_role is rejected (single-owner invariant).
    with pytest.raises(sharing.InvalidRoleError):
        await sharing.change_role(db_session, project.id, owner.id, member.id, "owner")
