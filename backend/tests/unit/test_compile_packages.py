"""Unit tests for the Tectonic package config loader (spec 21)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inkstave.compile.packages import (
    PackageConfigError,
    build_prewarm_document,
    load_package_config,
)
from inkstave.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_TOML = REPO_ROOT / "infra" / "tectonic" / "packages.toml"


def test_loads_real_packages_toml() -> None:
    config = load_package_config(PACKAGES_TOML, get_settings())
    prewarm = config.prewarm_packages()
    assert "amsmath" in prewarm
    assert "hyperref" in prewarm
    assert config.allow_network_fetch() is True
    assert config.bundle_url() is None  # empty url in the file
    assert config.cache_dir() == Path(get_settings().tectonic_cache_dir)


def test_missing_file_uses_env_defaults(tmp_path: Path) -> None:
    config = load_package_config(tmp_path / "nope.toml", get_settings())
    assert config.prewarm_packages() == []
    assert config.allow_network_fetch() is True
    assert config.cache_dir() == Path(get_settings().tectonic_cache_dir)


def test_malformed_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "packages.toml"
    bad.write_text("this is = = not valid toml [", encoding="utf-8")
    with pytest.raises(PackageConfigError):
        load_package_config(bad, get_settings())


def test_policy_disables_network_fetch(tmp_path: Path) -> None:
    cfg = tmp_path / "packages.toml"
    cfg.write_text("[policy]\nallow_network_fetch = false\n", encoding="utf-8")
    assert load_package_config(cfg, get_settings()).allow_network_fetch() is False


def test_build_prewarm_document() -> None:
    config = load_package_config(PACKAGES_TOML, get_settings())
    doc = build_prewarm_document(config)
    assert "\\documentclass{article}" in doc
    assert "\\usepackage{amsmath}" in doc
    assert "\\begin{document}" in doc
