"""The role → capability matrix is exhaustive and matches spec 34 §5.2."""

from __future__ import annotations

import pytest

from inkstave.authorization.capabilities import Capability, capabilities_for
from inkstave.db.models.membership import MembershipRole

C = Capability

# Authoritative expected matrix (spec 34 §5.2), viewer-compile enabled.
_EXPECTED: dict[MembershipRole | None, set[Capability]] = {
    MembershipRole.owner: set(Capability),
    MembershipRole.editor: {
        C.PROJECT_READ,
        C.DOC_READ,
        C.DOC_WRITE,
        C.FILE_READ,
        C.FILE_WRITE,
        C.COLLAB_READ,
        C.COLLAB_WRITE,
        C.COMPILE,
    },
    MembershipRole.viewer: {
        C.PROJECT_READ,
        C.DOC_READ,
        C.FILE_READ,
        C.COLLAB_READ,
        C.COMPILE,
    },
    None: set(),
}

_ROLES = [MembershipRole.owner, MembershipRole.editor, MembershipRole.viewer, None]


@pytest.mark.parametrize("role", _ROLES)
@pytest.mark.parametrize("cap", list(Capability))
def test_every_role_capability_pair(role: MembershipRole | None, cap: Capability) -> None:
    allowed = cap in capabilities_for(role)
    assert allowed is (cap in _EXPECTED[role]), f"{role} / {cap}"


def test_owner_has_all_capabilities() -> None:
    assert capabilities_for(MembershipRole.owner) == frozenset(Capability)


def test_non_member_has_no_capabilities() -> None:
    assert capabilities_for(None) == frozenset()


def test_viewer_compile_flag_toggles_compile() -> None:
    with_compile = capabilities_for(MembershipRole.viewer, compile_for_viewers=True)
    without = capabilities_for(MembershipRole.viewer, compile_for_viewers=False)
    assert Capability.COMPILE in with_compile
    assert Capability.COMPILE not in without
    # The flag only affects COMPILE — nothing else changes.
    assert with_compile - without == {Capability.COMPILE}
