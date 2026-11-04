"""Unit tests for comment anchors and excerpts (spec 118). No database here."""

from __future__ import annotations

import base64

import pytest

from inkstave.modules.discussion.comments.anchors import ANCHOR_MAX_B64_CHARS, decode_anchor, encode_anchor
from inkstave.modules.discussion.comments.outcome import EXCERPT_MAX_CHARS, excerpt


def test_anchor_round_trips_its_bytes() -> None:
    raw = bytes(range(40))
    assert decode_anchor(encode_anchor(raw)) == raw


def test_longest_allowed_anchor_is_accepted() -> None:
    raw = b"\x07" * 256
    value = base64.b64encode(raw).decode("ascii")
    assert len(value) == ANCHOR_MAX_B64_CHARS
    assert decode_anchor(value) == raw


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty
        "not base64!!",  # not base64
        base64.b64encode(b"\x01" * 257).decode("ascii"),  # one byte over the limit
    ],
)
def test_bad_anchors_are_refused(value: str) -> None:
    with pytest.raises(ValueError):
        decode_anchor(value)


def test_mention_e_mail_escapes_the_comment_text() -> None:
    from inkstave.infra.mailer.templates import render_email

    subject, text, html = render_email(
        "comment_mention",
        {
            "author_name": "Ana",
            "project_name": "Paper <b>",
            "excerpt": "<script>x</script>",
            "comment_url": "http://localhost/projects/p?thread=t",
        },
    )
    assert subject == "Ana mentioned you in Paper <b> on Inkstave"
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "http://localhost/projects/p?thread=t" in text


def test_excerpt_keeps_short_bodies_and_cuts_long_ones() -> None:
    assert excerpt("short") == "short"
    long_body = "x" * 500
    cut = excerpt(long_body)
    assert len(cut) == EXCERPT_MAX_CHARS
    assert cut.endswith("…")
