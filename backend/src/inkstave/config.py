"""Application settings.

A single typed settings object, populated from the environment / ``.env`` and
validated once at startup. Reach settings through :func:`get_settings` (cached)
or the :func:`inkstave.dependencies.get_settings_dep` FastAPI dependency — never
by reading ``os.environ`` in request code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration for the Inkstave backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Inkstave"
    environment: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    docs_enabled: bool = True

    # ``NoDecode`` stops pydantic-settings from JSON-decoding the raw env value
    # so the validator below can accept a plain comma-separated string too.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    redis_url: str = "redis://localhost:6379/0"
    # Reserved for spec 03 (database layer): read but unused here. Optional so
    # the app never fails to construct when it is absent (e.g. in tests).
    database_url: str | None = None

    request_id_header: str = "X-Request-ID"

    # Argon2id password-hashing parameters (spec 06). Defaults match argon2-cffi;
    # tests lower these so hashing is sub-millisecond and the suite stays fast.
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    # JWT authentication (spec 07). jwt_secret is required (no default) so the
    # app fails fast if it is unset. jwt_secret_previous holds retired secrets
    # accepted for verification only, enabling zero-downtime secret rotation.
    jwt_secret: str
    jwt_secret_previous: Annotated[list[str], NoDecode] = []
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "inkstave"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600

    # Rate limiting (spec 08). Values are "<limit>/<window_seconds>". The limiter
    # fails open if Redis is unavailable.
    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/300"
    rate_limit_register: str = "5/3600"
    rate_limit_refresh: str = "30/300"
    # Header carrying the real client IP behind a trusted proxy.
    trusted_proxy_header: str = "X-Forwarded-For"
    # WebSocket close code for an unauthorized connection (contract for spec 29).
    ws_auth_close_code: int = 4401

    # Max UTF-8 byte length of a single document on replace (spec 13).
    max_document_bytes: int = 2_000_000

    # Binary file storage (spec 14).
    file_storage_backend: Literal["local", "s3"] = "local"
    file_storage_local_path: str = "./data/files"
    max_upload_bytes: int = 52_428_800  # 50 MB
    allowed_upload_mime: Annotated[list[str], NoDecode] = [
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "application/pdf",
        "text/plain",
        "application/x-bibtex",
        "text/x-bibtex",
    ]
    storage_stream_chunk_bytes: int = 65_536
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    # LaTeX compilation via Tectonic (spec 21).
    tectonic_bin: str = "tectonic"
    tectonic_cache_dir: str = "/var/cache/tectonic"
    tectonic_bundle_url: str = ""
    tectonic_offline: bool = False
    compile_workdir_root: str = "/tmp/inkstave-compiles"
    tectonic_compile_timeout_s: int = 60
    compile_max_input_files: int = 2000
    compile_max_input_bytes: int = 104_857_600  # 100 MiB
    compile_max_output_bytes: int = 104_857_600  # 100 MiB
    compile_max_log_bytes: int = 2_097_152  # 2 MiB
    compile_max_stdout_bytes: int = 262_144  # 256 KiB
    compile_cpu_seconds: int | None = 60
    compile_address_space_bytes: int | None = 2_147_483_648  # 2 GiB
    compile_keep_workdir_on_failure: bool = False

    # Compile output storage & retention (spec 23).
    compile_output_prefix: str = "compiles"
    compile_retain_per_project: int = 10
    compile_retention_max_age_s: int = 2_592_000  # 30 days
    compile_retention_sweep_s: int = 3600
    compile_retention_batch: int = 200
    compile_pdf_cache_max_age_s: int = 60

    # Async compile API / ARQ jobs (spec 22).
    compile_max_concurrent_per_project: int = 1
    compile_max_concurrent_per_user: int = 3
    compile_debounce_coalesce: bool = True
    compile_job_timeout_s: int = 120
    compile_queue_name: str = "compiles"
    compile_sse_keepalive_s: int = 15
    compile_cancel_flag_ttl_s: int = 300

    @field_validator("compile_cpu_seconds", "compile_address_space_bytes", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        """An empty env value disables the (optional) rlimit."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("cors_origins", "jwt_secret_previous", "allowed_upload_mime", mode="before")
    @classmethod
    def _parse_str_list(cls, value: object) -> object:
        """Accept a JSON array or a comma-separated string for list settings."""
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_s3_bucket(self) -> Settings:
        if self.file_storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when FILE_STORAGE_BACKEND=s3")
        return self

    @model_validator(mode="after")
    def _job_timeout_exceeds_engine(self) -> Settings:
        # The engine's own timeout must fire first (clean TIMEOUT result) before
        # the ARQ job is killed mid-flight (mirrors Overleaf's lock>compile rule).
        if self.compile_job_timeout_s <= self.tectonic_compile_timeout_s:
            raise ValueError(
                "COMPILE_JOB_TIMEOUT_S must be strictly greater than TECTONIC_COMPILE_TIMEOUT_S"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance — the single construction point."""
    # Required fields (e.g. jwt_secret) are populated from the environment by
    # pydantic-settings, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
