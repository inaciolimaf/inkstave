"""Unit tests for tree-entity name path-safety validation."""

from __future__ import annotations

import pytest

from inkstave.services.safe_path import InvalidNameError, validate_name_segment


@pytest.mark.parametrize(
    "name",
    [
        "main.tex",
        "figures",
        "a file with spaces.txt",
        "résumé.tex",
        "  trimme.tex  ",  # surrounding whitespace is stripped
        "x" * 255,
        "console.tex",  # not reserved (stem is "console")
    ],
)
def test_valid_names(name: str) -> None:
    result = validate_name_segment(name)
    assert result == name.strip()


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        ".",
        "..",
        "a/b",
        "a\\b",
        "with\x00nul",
        "ctrl\x1fchar",
        "del\x7fchar",  # DEL (0x7f) is rejected as an ASCII control char
        "trailingdot.",
        "x" * 256,
        "con",
        "CON",
        "con.tex",
        "nul",
        "com1",
        "LPT9",
    ],
)
def test_invalid_names(name: str) -> None:
    with pytest.raises(InvalidNameError):
        validate_name_segment(name)
