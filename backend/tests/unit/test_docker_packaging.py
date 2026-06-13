"""Spec-56 static assertions over the production packaging files.

These are pure file parsing/string checks (milliseconds) — image builds and the
running stack are exercised by the out-of-budget CI job (spec 57), never here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE = _ROOT / "docker-compose.prod.yml"
_NGINX_MAIN = _ROOT / "infra" / "nginx" / "nginx.conf"
_NGINX_SERVER = _ROOT / "infra" / "nginx" / "default.conf"
_DOCKERIGNORE = _ROOT / ".dockerignore"
_PACKAGES = _ROOT / "infra" / "tectonic" / "packages.toml"
_BACKEND_DOCKERFILE = _ROOT / "backend" / "Dockerfile"
_FRONTEND_DOCKERFILE = _ROOT / "frontend" / "Dockerfile"

_SECRET_HINT = ("password", "secret", "api_key", "apikey", "token")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(_COMPOSE.read_text("utf-8"))


# --- docker-compose.prod.yml --------------------------------------------------- #


def test_expected_services_present(compose: dict) -> None:
    services = compose["services"]
    assert {"postgres", "redis", "backend", "worker", "frontend"} <= set(services)
    # Collab is in-app (no separate process) — see the ADR.
    assert "collab" not in services


def test_only_frontend_exposes_a_port_under_a_managed_proxy(compose: dict) -> None:
    # Under a managed proxy (Coolify/Traefik) the host's :80/:443 belong to that
    # proxy, so no service publishes a host `ports:` mapping — the frontend only
    # `expose`s :80 on the internal network for the proxy to route to.
    services = compose["services"]
    assert services["frontend"].get("expose") == ["80"], "frontend must expose :80"
    for name in ("postgres", "redis", "backend", "worker", "frontend"):
        assert "ports" not in services[name], f"{name} must not host-publish a port"


def test_long_running_services_restart_and_healthcheck(compose: dict) -> None:
    services = compose["services"]
    for name in ("postgres", "redis", "backend", "worker", "frontend"):
        svc = services[name]
        assert svc.get("restart") == "unless-stopped", name
        assert "healthcheck" in svc and "test" in svc["healthcheck"], name


def test_app_services_use_env_file_and_wait_for_deps(compose: dict) -> None:
    services = compose["services"]
    for name in ("backend", "worker"):
        assert services[name].get("env_file") == ".env", name
        deps = services[name]["depends_on"]
        assert deps["postgres"]["condition"] == "service_healthy"
        assert deps["redis"]["condition"] == "service_healthy"


def test_no_inline_secret_literals(compose: dict) -> None:
    # Every secret-ish env value must be a ${VAR} reference, never a baked literal.
    for name, svc in compose["services"].items():
        env = svc.get("environment", {})
        items = env.items() if isinstance(env, dict) else (e.split("=", 1) for e in env)
        for key, value in items:
            value = "" if value is None else str(value)
            if any(h in key.lower() for h in _SECRET_HINT) or any(
                h in value.lower() for h in _SECRET_HINT
            ):
                assert "${" in value or value == "", (
                    f"{name}.{key} bakes a secret literal: {value!r}"
                )


def test_expected_named_volumes_declared(compose: dict) -> None:
    volumes = compose.get("volumes", {})
    assert {"pgdata", "uploads", "tectonic-cache"} <= set(volumes)
    # Ephemeral per-compile workdirs must NOT be a shared named volume.
    assert "compiles" not in volumes and "workdir" not in volumes


def test_packages_toml_baked_into_image_and_tectonic_cache_mounted(compose: dict) -> None:
    # packages.toml is baked into the image (a bind mount breaks Coolify, which has
    # no repo checkout at deploy time); the Tectonic cache is still a named volume
    # shared by backend + worker so the format/bundle warmup persists across runs.
    dockerfile = _BACKEND_DOCKERFILE.read_text("utf-8")
    assert "infra/tectonic/packages.toml" in dockerfile, "packages.toml must be baked in"
    for name in ("backend", "worker"):
        mounts = compose["services"][name].get("volumes", [])
        assert any("/var/cache/tectonic" in m for m in mounts), name


# --- nginx reverse proxy ------------------------------------------------------- #


def test_nginx_main_has_gzip_and_no_server_tokens() -> None:
    main = _NGINX_MAIN.read_text("utf-8")
    assert "server_tokens off;" in main
    assert "gzip on;" in main


def test_nginx_api_proxies_to_backend() -> None:
    server = _NGINX_SERVER.read_text("utf-8")
    assert "location /api/" in server
    assert "proxy_pass http://backend:8000;" in server
    assert "client_max_body_size 50m;" in server


def test_nginx_ws_upgrade_headers() -> None:
    server = _NGINX_SERVER.read_text("utf-8")
    assert "location /ws/" in server
    assert "proxy_http_version 1.1;" in server
    assert "proxy_set_header Upgrade $http_upgrade;" in server
    assert 'proxy_set_header Connection "upgrade";' in server


def test_nginx_blocks_metrics_without_upstream() -> None:
    server = _NGINX_SERVER.read_text("utf-8")
    block = server.split("location /metrics")[1].split("}")[0]
    assert "return 404;" in block or "return 403;" in block
    assert "proxy_pass" not in block, "/metrics must never be proxied upstream"


def test_nginx_spa_fallback() -> None:
    server = _NGINX_SERVER.read_text("utf-8")
    assert "try_files $uri $uri/ /index.html;" in server


# --- .dockerignore ------------------------------------------------------------- #


def test_dockerignore_excludes_secrets_tests_caches() -> None:
    body = _DOCKERIGNORE.read_text("utf-8")
    patterns = [
        line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert ".env" in patterns
    assert any("node_modules" in p for p in patterns)
    assert any(".venv" in p for p in patterns)
    assert any("tests" in p for p in patterns)
    assert any("__pycache__" in p for p in patterns)


# --- Dockerfiles --------------------------------------------------------------- #


def test_backend_dockerfile_multistage_alpine_nonroot() -> None:
    body = _BACKEND_DOCKERFILE.read_text("utf-8")
    assert "FROM python:3.12-alpine AS builder" in body
    assert "FROM python:3.12-alpine AS runtime" in body
    assert "USER inkstave" in body
    assert "tectonic" in body  # the LaTeX engine is installed
    assert "uv sync --frozen --no-dev" in body


def test_frontend_dockerfile_builds_then_serves_with_nginx() -> None:
    body = _FRONTEND_DOCKERFILE.read_text("utf-8")
    assert "FROM node:20-alpine AS builder" in body
    assert "FROM nginx:1.27-alpine AS runtime" in body
    assert "pnpm build" in body
    # No Node toolchain in the runtime stage: nothing after the nginx FROM installs node.
    runtime = body.split("AS runtime", 1)[1]
    assert "node" not in runtime.lower()


# --- infra/tectonic/packages.toml ---------------------------------------------- #


def test_packages_toml_parses_and_documents_how_to_add() -> None:
    text = _PACKAGES.read_text("utf-8")
    data = tomllib.loads(text)
    assert "packages" in data and "prewarm" in data["packages"]
    assert "How to add a package" in text
