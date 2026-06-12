"""Unit tests for LocalTectonicRunner argv construction — no process spawned (spec 21)."""

from __future__ import annotations

from pathlib import Path

from inkstave.compile.runner import LocalTectonicRunner


def _runner(*, offline: bool = False, bundle_url: str | None = None) -> LocalTectonicRunner:
    return LocalTectonicRunner(
        bin_path="tectonic",
        cache_dir=Path("/var/cache/tectonic"),
        bundle_url=bundle_url,
        offline=offline,
    )


def test_argv_is_a_no_shell_list_targeting_output_dir() -> None:
    cmd = _runner().build_command(main_file="main.tex", output_dir=Path("/wd/output"))
    assert isinstance(cmd.argv, list)
    assert cmd.argv[0] == "tectonic"
    assert "compile" in cmd.argv
    assert "main.tex" in cmd.argv
    # Outputs go to a dedicated output dir.
    idx = cmd.argv.index("--outdir")
    assert cmd.argv[idx + 1] == "/wd/output"
    assert "--synctex" in cmd.argv
    # Cache points at TECTONIC_CACHE_DIR via env.
    assert cmd.env["TECTONIC_CACHE_DIR"] == "/var/cache/tectonic"
    # Online by default: no offline flag.
    assert "--only-cached" not in cmd.argv


def test_offline_adds_only_cached_flag() -> None:
    cmd = _runner(offline=True).build_command(main_file="main.tex", output_dir=Path("/wd/output"))
    assert "--only-cached" in cmd.argv


def test_bundle_url_added_when_set() -> None:
    cmd = _runner(bundle_url="https://example/bundle.tar").build_command(
        main_file="main.tex", output_dir=Path("/wd/output")
    )
    idx = cmd.argv.index("--bundle")
    assert cmd.argv[idx + 1] == "https://example/bundle.tar"
