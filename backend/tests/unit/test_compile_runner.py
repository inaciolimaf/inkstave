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


def test_compile_sandbox_no_shell_escape_no_inherited_secrets(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # spec 52 §5.4: shell-escape/\write18 is off (Tectonic has no such flag) and the
    # compile env never inherits application secrets.
    monkeypatch.setenv("JWT_SECRET", "super-secret-value")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-leak")
    cmd = _runner().build_command(main_file="main.tex", output_dir=Path("/wd/output"))
    joined = " ".join(cmd.argv).lower()
    assert "shell-escape" not in joined and "write18" not in joined and "-shell" not in joined
    assert "JWT_SECRET" not in cmd.env and "OPENROUTER_API_KEY" not in cmd.env
    assert "super-secret-value" not in " ".join(cmd.env.values())
    assert set(cmd.env) <= {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TECTONIC_CACHE_DIR"}


def test_offline_adds_only_cached_flag() -> None:
    cmd = _runner(offline=True).build_command(main_file="main.tex", output_dir=Path("/wd/output"))
    assert "--only-cached" in cmd.argv


def test_bundle_url_added_when_set() -> None:
    cmd = _runner(bundle_url="https://example/bundle.tar").build_command(
        main_file="main.tex", output_dir=Path("/wd/output")
    )
    idx = cmd.argv.index("--bundle")
    assert cmd.argv[idx + 1] == "https://example/bundle.tar"
