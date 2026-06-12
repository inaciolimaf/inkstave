"""Isolated unit tests for spec-59 user schemas (spec 59 §8; spec 68 #247).

No HTTP/DB roundtrip — these validate the Pydantic models directly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inkstave.schemas.user import (
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    ChangePasswordRequest,
    EditorPreferences,
    UpdateProfileRequest,
)

# --- EditorPreferences font-size clamping + enum validation ------------------ #


def test_font_size_clamps_below_min() -> None:
    prefs = EditorPreferences(font_size=2)
    assert prefs.font_size == FONT_SIZE_MIN


def test_font_size_clamps_above_max() -> None:
    prefs = EditorPreferences(font_size=999)
    assert prefs.font_size == FONT_SIZE_MAX


def test_font_size_within_range_unchanged() -> None:
    assert EditorPreferences(font_size=16).font_size == 16


def test_theme_and_keymap_enum_rejected() -> None:
    with pytest.raises(ValidationError):
        EditorPreferences(theme="solarized")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EditorPreferences(keymap="sublime")  # type: ignore[arg-type]


def test_editor_preferences_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EditorPreferences(font_size=14, bogus=True)  # type: ignore[call-arg]


# --- UpdateProfileRequest display-name trimming + bounds --------------------- #


def test_display_name_is_trimmed() -> None:
    assert UpdateProfileRequest(display_name="  Ada  ").display_name == "Ada"


def test_display_name_blank_after_trim_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateProfileRequest(display_name="   ")


def test_display_name_too_long_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateProfileRequest(display_name="x" * 101)


def test_update_profile_all_optional() -> None:
    # Both fields omitted is valid (the route decides "at least one").
    req = UpdateProfileRequest()
    assert req.display_name is None
    assert "avatar_url" not in req.model_fields_set


# --- ChangePasswordRequest reuses the password policy ----------------------- #


def test_change_password_rejects_weak_password() -> None:
    # No digit -> spec-06 charset rule rejects it.
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old", new_password="lettersonly")
    # Too short -> length bound rejects it.
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="old", new_password="ab1")


def test_change_password_accepts_strong_password() -> None:
    req = ChangePasswordRequest(current_password="old", new_password="newpass123")
    assert req.new_password == "newpass123"
