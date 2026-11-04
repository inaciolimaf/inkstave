"""Share-link tokens never reach the access log (spec 116).

uvicorn's access logger prints the raw request path, so the token segment of
``/share-links/{token}`` must be masked there. The rest of the path stays readable.
"""

from __future__ import annotations

import logging

import pytest

from inkstave.core.observability.log import SecretPathFilter, redact_path


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("/api/v1/share-links/SECRET/join", "/api/v1/share-links/***REDACTED***/join"),
        ("/api/v1/share-links/SECRET", "/api/v1/share-links/***REDACTED***"),
        ("/api/v1/invites/SECRET/accept", "/api/v1/invites/***REDACTED***/accept"),
        ("/join?token=SECRET&x=1", "/join?token=***REDACTED***&x=1"),
        ("/api/v1/projects/p1/share-links", "/api/v1/projects/p1/share-links"),
    ],
)
def test_redact_path_masks_only_the_token(raw: str, masked: str) -> None:
    assert redact_path(raw) == masked


def test_access_log_record_is_masked_before_it_is_formatted() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", "/api/v1/share-links/SECRET-TOKEN", "1.1", 200),
        None,
    )

    assert SecretPathFilter().filter(record) is True

    assert "SECRET-TOKEN" not in record.getMessage()
    assert record.getMessage() == '10.0.0.1:5000 - "GET /api/v1/share-links/***REDACTED*** HTTP/1.1" 200'
