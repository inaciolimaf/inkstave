"""Unit tests for content-type sniffing (spec 14, covered in the spec-15 pass)."""

from __future__ import annotations

import pytest

from inkstave.services.file_service import sniff_content_type


@pytest.mark.parametrize(
    ("head", "declared", "expected"),
    [
        (b"\x89PNG\r\n\x1a\n\x00\x00", None, "image/png"),
        (b"\xff\xd8\xff\xe0", None, "image/jpeg"),
        (b"GIF89a....", None, "image/gif"),
        (b"%PDF-1.7", None, "application/pdf"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", None, "image/webp"),
        (b"plain text", "text/plain", "text/plain"),  # falls back to declared
        (b"unknown bytes", None, "application/octet-stream"),  # default
    ],
)
def test_sniff_content_type(head: bytes, declared: str | None, expected: str) -> None:
    assert sniff_content_type(head, declared) == expected
