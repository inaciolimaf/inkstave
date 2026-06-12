"""Loads ``infra/tectonic/packages.toml`` into a typed config (spec 21).

This is declarative configuration (not code): a deployer pins the bundle,
declares a prewarm set, and toggles the network-fetch policy without touching
source. Missing file → env-backed defaults; malformed file → a clear error.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from inkstave.compile.errors import CompileError

if TYPE_CHECKING:
    from inkstave.config import Settings


class PackageConfigError(CompileError):
    """The packages.toml file is present but malformed."""


@dataclass(slots=True, frozen=True)
class PackageConfig:
    _bundle_url: str | None
    _cache_dir: Path
    _prewarm: tuple[str, ...]
    _allow_network_fetch: bool
    format: str

    def bundle_url(self) -> str | None:
        return self._bundle_url

    def cache_dir(self) -> Path:
        return self._cache_dir

    def prewarm_packages(self) -> list[str]:
        return list(self._prewarm)

    def allow_network_fetch(self) -> bool:
        return self._allow_network_fetch


def load_package_config(path: Path, settings: Settings) -> PackageConfig:
    """Load packages.toml, falling back to settings/env defaults when absent."""
    data: dict[str, object] = {}
    if path.is_file():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise PackageConfigError(f"Invalid packages config at {path}: {exc}") from exc

    def _section(key: str) -> dict[str, object]:
        value = data.get(key, {})
        if not isinstance(value, dict):
            raise PackageConfigError(f"Section [{key}] in {path} must be a table")
        return value

    bundle = _section("bundle")
    cache = _section("cache")
    packages = _section("packages")
    policy = _section("policy")

    bundle_url = str(bundle.get("url") or "") or settings.tectonic_bundle_url
    cache_dir = str(cache.get("dir") or "") or settings.tectonic_cache_dir
    prewarm_raw = packages.get("prewarm", [])
    prewarm = tuple(str(p) for p in prewarm_raw) if isinstance(prewarm_raw, list) else ()
    allow_network = bool(policy.get("allow_network_fetch", True))
    fmt = str(bundle.get("format") or "latex")

    return PackageConfig(
        _bundle_url=bundle_url or None,
        _cache_dir=Path(cache_dir),
        _prewarm=prewarm,
        _allow_network_fetch=allow_network,
        format=fmt,
    )


def build_prewarm_document(config: PackageConfig) -> str:
    """A tiny ``.tex`` that ``\\usepackage``s the prewarm set.

    A build step compiles this once to warm ``TECTONIC_CACHE_DIR`` so the image
    ships with those packages and offline first-compiles work. It is out of the
    request hot path (stubbed in tests).
    """
    uses = "\n".join(f"\\usepackage{{{pkg}}}" for pkg in config.prewarm_packages())
    return f"\\documentclass{{article}}\n{uses}\n\\begin{{document}}\nprewarm\n\\end{{document}}\n"
