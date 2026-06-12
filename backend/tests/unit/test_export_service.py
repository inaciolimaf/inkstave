"""Unit tests for the export filename/header helpers (spec 102)."""

from __future__ import annotations

from inkstave.services.export_service import content_disposition, zip_filename_for


def test_zip_filename_sanitizes_quotes_slashes_and_crlf() -> None:
    assert zip_filename_for('My "Thesis"/v2\n') == "My Thesis v2.zip"


def test_zip_filename_collapses_whitespace_and_trims() -> None:
    assert zip_filename_for("  a   b  ") == "a b.zip"


def test_zip_filename_falls_back_to_project() -> None:
    assert zip_filename_for("") == "project.zip"
    assert zip_filename_for("///") == "project.zip"


def test_content_disposition_has_ascii_and_rfc5987_forms() -> None:
    cd = content_disposition(zip_filename_for("Café"))
    assert cd.startswith("attachment; ")
    assert 'filename="Caf' in cd  # non-ASCII replaced in the plain form
    assert "filename*=UTF-8''Caf%C3%A9.zip" in cd  # percent-encoded UTF-8 form


def test_content_disposition_strips_quotes_and_crlf_from_ascii_form() -> None:
    cd = content_disposition('a"b\r\n.zip')
    assert '"' not in cd.split("filename*=")[0].replace('filename="', "").replace('";', "")
    assert "\r" not in cd and "\n" not in cd
