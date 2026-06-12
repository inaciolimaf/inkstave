"""Unit tests for the AppError hierarchy and error envelope model."""

from __future__ import annotations

from inkstave.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    ErrorBody,
    ErrorEnvelope,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)


def test_subclass_status_and_type() -> None:
    cases = [
        (BadRequestError, 400, "bad_request"),
        (UnauthorizedError, 401, "unauthorized"),
        (ForbiddenError, 403, "forbidden"),
        (NotFoundError, 404, "not_found"),
        (ConflictError, 409, "conflict"),
    ]
    for cls, status, error_type in cases:
        exc = cls("boom")
        assert isinstance(exc, AppError)
        assert exc.status_code == status
        assert exc.error_type == error_type
        assert exc.message == "boom"
        assert exc.details is None


def test_details_are_carried() -> None:
    details = [{"loc": ["body", "x"], "msg": "bad", "type": "value_error"}]
    exc = BadRequestError("nope", details=details)
    assert exc.details == details


def test_envelope_shape() -> None:
    env = ErrorEnvelope(error=ErrorBody(type="not_found", message="missing", request_id="abc"))
    dumped = env.model_dump()
    assert dumped["error"]["type"] == "not_found"
    assert dumped["error"]["message"] == "missing"
    assert dumped["error"]["request_id"] == "abc"
    assert dumped["error"]["details"] is None
