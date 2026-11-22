"""The last active admin cannot be removed, so the public first-admin setup stays closed.

``POST /api/setup/admin`` opens again once no admin is left (it only checks
``is_admin`` rows), so deleting or deactivating the last active admin must be refused.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave import cli
from inkstave.core.config.settings import get_settings
from inkstave.core.errors import ConflictError
from inkstave.modules.auth.accounts.account import deactivate_account
from inkstave.modules.auth.accounts.users import normalise_email
from inkstave.modules.auth.credentials.password import build_password_hasher
from inkstave.modules.auth.credentials.tokens import build_token_service
from inkstave.modules.auth.models.user import User

pytestmark = pytest.mark.integration

PASSWORD = "Sup3rPass"
SETUP = "/api/setup"
USERS = "/api/v1/users"


async def _user(db: AsyncSession, email: str, *, admin: bool = False, active: bool = True) -> User:
    hasher = build_password_hasher(get_settings())
    user = User(
        email=normalise_email(email),
        hashed_password=hasher.hash(PASSWORD),
        display_name=email.split("@", 1)[0],
        is_admin=admin,
        is_active=active,
        email_confirmed=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token, _ = build_token_service(get_settings()).create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


async def test_the_only_admin_cannot_delete_their_account(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "root@example.com", admin=True)

    response = await async_client.request(
        "DELETE", f"{USERS}/me", json={"password": PASSWORD, "confirm": True}, headers=_headers(admin)
    )

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "conflict"
    await db_session.refresh(admin)
    assert admin.is_active is True


async def test_setup_stays_locked_when_the_last_admin_is_protected(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "root@example.com", admin=True)
    await async_client.request(
        "DELETE", f"{USERS}/me", json={"password": PASSWORD, "confirm": True}, headers=_headers(admin)
    )

    body = {"email": "intruder@example.com", "password": "Intrud3rPass", "display_name": "X"}
    assert (await async_client.post(f"{SETUP}/admin", json=body)).status_code == 409


async def test_an_admin_can_delete_their_account_when_another_active_admin_exists(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "one@example.com", admin=True)
    await _user(db_session, "two@example.com", admin=True)

    response = await async_client.request(
        "DELETE", f"{USERS}/me", json={"password": PASSWORD, "confirm": True}, headers=_headers(admin)
    )

    assert response.status_code == 204


async def test_a_deactivated_admin_does_not_count_as_a_remaining_admin(db_session: AsyncSession) -> None:
    last = await _user(db_session, "last@example.com", admin=True)
    await _user(db_session, "gone@example.com", admin=True, active=False)

    with pytest.raises(ConflictError):
        await deactivate_account(db_session, last)


async def test_deactivating_the_last_active_admin_is_refused(db_session: AsyncSession) -> None:
    admin = await _user(db_session, "solo@example.com", admin=True)

    with pytest.raises(ConflictError):
        await deactivate_account(db_session, admin)
    await db_session.refresh(admin)
    assert admin.is_active is True


async def test_deactivating_an_admin_is_allowed_when_another_active_one_remains(
    db_session: AsyncSession,
) -> None:
    first = await _user(db_session, "first@example.com", admin=True)
    await _user(db_session, "second@example.com", admin=True)

    await deactivate_account(db_session, first)

    assert first.is_active is False


async def test_deactivating_a_regular_user_is_unaffected(db_session: AsyncSession) -> None:
    await _user(db_session, "admin@example.com", admin=True)
    regular = await _user(db_session, "regular@example.com")

    await deactivate_account(db_session, regular)

    assert regular.is_active is False


class _SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _EngineStub:
    async def dispose(self) -> None:
        return None


async def test_cli_deactivate_user_refuses_the_last_active_admin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    db_session: AsyncSession,
) -> None:
    await _user(db_session, "cli-root@example.com", admin=True)
    monkeypatch.setattr(
        cli,
        "create_engine_and_sessionmaker",
        lambda _settings: (_EngineStub(), lambda: _SessionContext(db_session)),
    )

    code = await cli._cmd_deactivate_user("cli-root@example.com")

    assert code == 1
    assert "FAIL" in capsys.readouterr().err
