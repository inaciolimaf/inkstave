"""Spell-check API (spec 113): project language and the personal dictionary."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.config.settings import get_settings
from inkstave.modules.auth.accounts import dictionary
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from tests.factories import UserFactory

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"
DICTIONARY = "/api/v1/me/dictionary"


async def _user(db_session: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await UserFactory.create(db_session)
    await db_session.commit()
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return user, {"Authorization": f"Bearer {token}"}


async def _member(db_session: AsyncSession, project_id: str, user_id: Any, role: MembershipRole) -> None:
    db_session.add(
        ProjectMembership(
            project_id=UUID(project_id), user_id=user_id, role=role, status=MembershipStatus.active
        )
    )
    await db_session.commit()


async def test_new_project_defaults_to_en_us_and_takes_the_creators_language(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, headers = await _user(db_session)
    default = await async_client.post(PROJECTS, json={"name": "Paper"}, headers=headers)
    assert default.status_code == 201
    assert default.json()["spellcheck_language"] == "en-US"
    pt = await async_client.post(
        PROJECTS, json={"name": "Tese", "spellcheck_language": "pt-BR"}, headers=headers
    )
    assert pt.json()["spellcheck_language"] == "pt-BR"
    bad = await async_client.post(
        PROJECTS, json={"name": "X", "spellcheck_language": "fr-FR"}, headers=headers
    )
    assert bad.status_code == 422


async def test_editor_changes_the_language_and_viewer_cannot(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_h = await _user(db_session)
    created = await async_client.post(PROJECTS, json={"name": "Paper"}, headers=owner_h)
    pid = created.json()["id"]
    editor, editor_h = await _user(db_session)
    await _member(db_session, pid, editor.id, MembershipRole.editor)
    viewer, viewer_h = await _user(db_session)
    await _member(db_session, pid, viewer.id, MembershipRole.viewer)
    url = f"{PROJECTS}/{pid}/settings"

    assert (
        await async_client.patch(url, json={"spellcheck_language": "pt-BR"}, headers=viewer_h)
    ).status_code == 403
    edited = await async_client.patch(url, json={"spellcheck_language": "pt-BR"}, headers=editor_h)
    assert edited.status_code == 200
    assert edited.json()["spellcheck_language"] == "pt-BR"
    assert (await async_client.get(f"{PROJECTS}/{pid}", headers=owner_h)).json()[
        "spellcheck_language"
    ] == "pt-BR"

    off = await async_client.patch(url, json={"spellcheck_language": "off"}, headers=owner_h)
    assert off.json()["spellcheck_language"] == "off"
    invalid = await async_client.patch(url, json={"spellcheck_language": "de-DE"}, headers=owner_h)
    assert invalid.status_code == 422


async def test_stranger_gets_404_for_project_settings(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, owner_h = await _user(db_session)
    pid = (await async_client.post(PROJECTS, json={"name": "Paper"}, headers=owner_h)).json()["id"]
    _, stranger_h = await _user(db_session)
    resp = await async_client.patch(
        f"{PROJECTS}/{pid}/settings", json={"spellcheck_language": "pt-BR"}, headers=stranger_h
    )
    assert resp.status_code == 404


async def test_dictionary_add_is_idempotent_and_case_insensitive(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, headers = await _user(db_session)
    assert (await async_client.get(DICTIONARY, headers=headers)).json() == {"words": []}
    first = await async_client.post(DICTIONARY, json={"word": "Inkstave"}, headers=headers)
    assert first.status_code == 201
    assert first.json() == {"word": "Inkstave"}
    again = await async_client.post(DICTIONARY, json={"word": "inkstave"}, headers=headers)
    assert again.status_code == 201
    listed = await async_client.get(DICTIONARY, headers=headers)
    assert listed.json() == {"words": ["Inkstave"]}


async def test_dictionary_is_per_user(async_client: AsyncClient, db_session: AsyncSession) -> None:
    _, alice = await _user(db_session)
    _, bob = await _user(db_session)
    await async_client.post(DICTIONARY, json={"word": "tectonic"}, headers=alice)
    assert (await async_client.get(DICTIONARY, headers=bob)).json() == {"words": []}


@pytest.mark.parametrize("word", ["", "   ", "two words", "tab\tinside", "x" * 65])
async def test_dictionary_rejects_invalid_words(
    async_client: AsyncClient, db_session: AsyncSession, word: str
) -> None:
    _, headers = await _user(db_session)
    resp = await async_client.post(DICTIONARY, json={"word": word}, headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["type"] == "validation_error"


async def test_dictionary_accepts_a_64_character_word(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, headers = await _user(db_session)
    resp = await async_client.post(DICTIONARY, json={"word": "a" * 64}, headers=headers)
    assert resp.status_code == 201


async def test_dictionary_delete_removes_the_word(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    _, headers = await _user(db_session)
    await async_client.post(DICTIONARY, json={"word": "and/or"}, headers=headers)
    deleted = await async_client.delete(f"{DICTIONARY}/and%2For", headers=headers)
    assert deleted.status_code == 204
    assert (await async_client.get(DICTIONARY, headers=headers)).json() == {"words": []}


async def test_dictionary_cap_answers_409(
    async_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dictionary, "MAX_WORDS", 2)
    _, headers = await _user(db_session)
    assert (await async_client.post(DICTIONARY, json={"word": "one"}, headers=headers)).status_code == 201
    assert (await async_client.post(DICTIONARY, json={"word": "two"}, headers=headers)).status_code == 201
    full = await async_client.post(DICTIONARY, json={"word": "three"}, headers=headers)
    assert full.status_code == 409
    assert full.json()["error"]["type"] == "dictionary_full"
    # An existing word is still accepted at the cap: it is a no-op, not a new entry.
    assert (await async_client.post(DICTIONARY, json={"word": "ONE"}, headers=headers)).status_code == 201
