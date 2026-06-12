"""Keyword-only signature guards (spec 96).

Cheap, in-memory introspection: the refactored parameters are keyword-only (so a
positional call raises TypeError), and the collab flush flag was split into two
intention-revealing public methods. No behaviour exercised here — the existing
collab/auth/CLI suites prove behaviour is unchanged.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from inkstave.auth.refresh_store import RefreshStore
from inkstave.cli import _cmd_seed
from inkstave.collab.manager import DocumentManager
from inkstave.collab.store import CrdtStore


def _all_keyword_only(func: Callable[..., Any], names: list[str]) -> bool:
    params = inspect.signature(func).parameters
    return all(params[n].kind is inspect.Parameter.KEYWORD_ONLY for n in names)


def test_cmd_seed_params_are_keyword_only() -> None:
    assert _all_keyword_only(_cmd_seed, ["demo", "force"])


def test_store_refresh_ids_are_keyword_only() -> None:
    assert _all_keyword_only(RefreshStore.store_refresh, ["jti", "user_id", "family_id"])


def test_snapshot_params_are_keyword_only() -> None:
    assert _all_keyword_only(
        CrdtStore.snapshot, ["document_id", "state", "state_vector", "upto_update_id"]
    )


def test_manager_exposes_intention_revealing_flush_methods() -> None:
    assert callable(DocumentManager.flush_text_now)
    assert callable(DocumentManager.flush_text_if_dirty)
    # The private force-flagged helper still exists (shared implementation).
    assert _all_keyword_only(DocumentManager._do_flush_text, ["force"])
