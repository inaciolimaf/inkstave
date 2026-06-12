"""Unit tests for the perf gate, network guard, and CRDT throughput (spec 53)."""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from pycrdt import Doc, Text

_GATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_test_budget.py"
_spec = importlib.util.spec_from_file_location("check_test_budget", _GATE_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules["check_test_budget"] = gate  # so the module's @dataclass resolves
_spec.loader.exec_module(gate)


# --- CI budget gate self-test (AC1, gate self-test) ------------------------- #


def test_gate_passes_under_budget() -> None:
    result = gate.evaluate({"total_s": 60, "slowest": []})
    assert result.ok


def test_gate_fails_over_budget() -> None:
    result = gate.evaluate({"total_s": 130, "slowest": []})
    assert not result.ok
    assert any("exceeds" in m for m in result.messages)


def test_gate_warns_in_headroom_band_but_passes() -> None:
    result = gate.evaluate({"total_s": 95, "slowest": []})
    assert result.ok
    assert any("WARN" in m for m in result.messages)


def test_gate_fails_a_slow_non_marked_test_but_excludes_slow_marked() -> None:  # AC5
    timing = {
        "total_s": 60,
        "slowest": [
            {"name": "test_heavy", "duration_s": 12, "slow_marked": False},
            {"name": "test_nightly", "duration_s": 40, "slow_marked": True},
        ],
    }
    result = gate.evaluate(timing)
    assert not result.ok
    assert any("test_heavy" in m and "FAIL" in m for m in result.messages)
    assert not any("test_nightly" in m for m in result.messages)  # @slow excluded


# --- CLI main() exit codes (spec 53 §8) ------------------------------------- #


def test_gate_main_exits_nonzero_over_budget(tmp_path: Any) -> None:
    timing = tmp_path / "test-timing.json"
    timing.write_text(json.dumps({"total_s": 130, "slowest": []}))
    assert gate.main(["check_test_budget.py", str(timing)]) == 1


def test_gate_main_exits_zero_under_budget(tmp_path: Any) -> None:
    timing = tmp_path / "test-timing.json"
    timing.write_text(json.dumps({"total_s": 60, "slowest": []}))
    assert gate.main(["check_test_budget.py", str(timing)]) == 0


# --- outbound-network guard (AC3) ------------------------------------------- #


def test_real_network_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="Real network access"):
        socket.getaddrinfo("api.openrouter.ai", 443)
    # Localhost / IP literals (the test DB) remain reachable.
    socket.getaddrinfo("127.0.0.1", 5432)


# --- CRDT throughput sanity (AC9) ------------------------------------------- #


def test_crdt_burst_converges_within_bound() -> None:
    a: Doc = Doc()
    b: Doc = Doc()
    a_text = a.get("content", type=Text)
    b_text = b.get("content", type=Text)
    updates: list[bytes] = []
    a.observe(lambda e: updates.append(e.update) if getattr(e, "update", None) else None)

    n = 500
    start = time.perf_counter()
    for _ in range(n):
        with a.transaction():
            a_text.insert(len(str(a_text)), "x")
    for update in updates:
        b.apply_update(update)
    elapsed = time.perf_counter() - start

    assert str(a_text) == "x" * n
    assert str(b_text) == str(a_text)  # collaborators converge
    assert elapsed < 3.0  # smoke bound — guards against an O(n^2) regression
