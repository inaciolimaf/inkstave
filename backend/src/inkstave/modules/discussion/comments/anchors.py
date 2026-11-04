"""Anchor bytes on the wire and in the database (spec 118, ADR 0118).

The client sends each relative position as standard base64. The server checks that it decodes and
fits the size limit, then stores the bytes. It never reads their content.
"""

from __future__ import annotations

import base64
import binascii

from inkstave.modules.discussion.comments.models import ANCHOR_MAX_BYTES

# Base64 of ANCHOR_MAX_BYTES bytes, with padding.
ANCHOR_MAX_B64_CHARS = 4 * ((ANCHOR_MAX_BYTES + 2) // 3)


def decode_anchor(value: str) -> bytes:
    """The raw anchor bytes for a base64 value. Raises ``ValueError`` when it is not one of ours."""
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("anchor is not valid base64") from exc
    if not raw:
        raise ValueError("anchor is empty")
    if len(raw) > ANCHOR_MAX_BYTES:
        raise ValueError(f"anchor is longer than {ANCHOR_MAX_BYTES} bytes")
    return raw


def encode_anchor(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
