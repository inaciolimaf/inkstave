"""The fast-tier speed guard must block a real Tectonic compile (spec 25).

This proves criteria 3–4: a real compile in a fast tier fails loudly via the
autouse ``_no_real_compile`` conftest fixture, instead of silently spawning the
``tectonic`` subprocess and blowing the suite's time budget.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.compile.limits import CancelToken, ResourceLimits
from inkstave.compile.runner import LocalTectonicRunner


def _limits() -> ResourceLimits:
    return ResourceLimits(
        max_input_files=10,
        max_input_bytes=1000,
        max_output_bytes=1000,
        max_log_bytes=1000,
        max_stdout_bytes=1000,
        cpu_seconds=None,
        address_space_bytes=None,
    )


async def test_real_runner_is_blocked_in_fast_tier(tmp_path: Path) -> None:
    runner = LocalTectonicRunner(
        bin_path="tectonic", cache_dir=tmp_path, bundle_url=None, offline=True
    )
    with pytest.raises(RuntimeError, match="Real Tectonic compile"):
        await runner.run(
            workdir=tmp_path,
            main_file="main.tex",
            output_dir=tmp_path,
            timeout_s=1,
            limits=_limits(),
            cancel=CancelToken(),
        )
