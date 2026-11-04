"""The body cap of the Git routes (spec 121 §5.3): a push has its own cap, larger than the JSON cap."""

from __future__ import annotations

from inkstave.core.config.settings import get_settings
from inkstave.core.http.body_limit import BodySizeLimitMiddleware


def _middleware() -> BodySizeLimitMiddleware:
    async def app(scope: object, receive: object, send: object) -> None:  # never called here
        raise AssertionError("the cap is computed without calling the app")

    return BodySizeLimitMiddleware(app, get_settings())


def test_git_receive_pack_has_the_push_cap() -> None:
    settings = get_settings()
    cap = _middleware()._cap("/api/v1/git/projects/abc.git/git-receive-pack")
    assert cap == settings.git_max_push_bytes
    assert cap > settings.max_request_body_bytes


def test_git_upload_pack_has_the_upload_cap_and_other_paths_the_json_cap() -> None:
    settings = get_settings()
    assert _middleware()._cap("/api/v1/git/projects/abc.git/git-upload-pack") == settings.max_upload_bytes
    assert _middleware()._cap("/api/v1/projects") == settings.max_request_body_bytes
