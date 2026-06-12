"""Application settings.

A single typed settings object, populated from the environment / ``.env`` and
validated once at startup. Reach settings through :func:`get_settings` (cached)
or the :func:`inkstave.dependencies.get_settings_dep` FastAPI dependency — never
by reading ``os.environ`` in request code.

The settings *fields* live in cohesive mixins in :mod:`inkstave.config_groups`
(purely to keep this module under its line budget); the mixin order here defines
the field order. All validators and guards stay below so they remain in one
place.
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from inkstave.config_groups import (
    AuthSettingsMixin,
    CollaborationSettingsMixin,
    CollabSettingsMixin,
    CompileSettingsMixin,
    CoreSettingsMixin,
    ImportSettingsMixin,
    SecuritySettingsMixin,
    StorageSettingsMixin,
)


class Settings(
    # Bases are listed in REVERSE of the desired field order: pydantic v2 builds
    # fields walking the MRO most-base-first, so the last base here contributes
    # the first fields. This ordering reproduces the original top-to-bottom order
    # (Core … Collaboration).
    CollaborationSettingsMixin,
    CollabSettingsMixin,
    CompileSettingsMixin,
    ImportSettingsMixin,
    StorageSettingsMixin,
    SecuritySettingsMixin,
    AuthSettingsMixin,
    CoreSettingsMixin,
    BaseSettings,
):
    """Environment-driven configuration for the Inkstave backend.

    Fields are defined by the mixin bases (see :mod:`inkstave.config_groups`);
    the inheritance order above preserves the canonical field/env order.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
        # Accept both the field name and its validation alias (spec 68 #219: legacy
        # CORS_ORIGINS / RATE_LIMIT_LOGIN kwargs and env vars keep working).
        populate_by_name=True,
    )

    @property
    def env_name(self) -> str:
        """Long-form environment name for the `env` log field."""
        return {"dev": "development", "test": "test", "prod": "production"}[self.environment]

    @field_validator("compile_cpu_seconds", "compile_address_space_bytes", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        """An empty env value disables the (optional) rlimit."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "cors_origins",
        "jwt_secret_previous",
        "allowed_upload_mime",
        "upload_allowed_extensions",
        "import_allowed_extensions",
        mode="before",
    )
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
    def _guard_production_secret(self) -> Settings:
        """Refuse to boot in production with a missing/weak/default JWT secret (spec 52)."""
        if self.environment != "prod":
            return self
        secret = self.jwt_secret or ""
        weak = {"changeme", "secret", "dev", "development", "test", "insecure", "default", "key"}
        if len(secret.encode()) < 32 or secret.lower() in weak:
            raise ValueError(
                "JWT_SECRET must be a strong, non-default value (>=32 bytes) in production"
            )
        return self

    @model_validator(mode="after")
    def _guard_production_cors(self) -> Settings:
        """A wildcard with credentials, or an empty allow-list in prod, is rejected."""
        if "*" in self.cors_origins:
            raise ValueError("CORS allow-list cannot be '*' (credentials are enabled)")
        if self.environment == "prod" and not self.cors_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must be set in production (no silent wildcard)")
        return self

    @model_validator(mode="after")
    def _guard_production_required(self) -> Settings:
        """Fail fast in production when a required connection var is missing (spec 57)."""
        if self.environment != "prod":
            return self
        missing = [name for name, value in (("DATABASE_URL", self.database_url),) if not value]
        # REDIS_URL has a default, so "unset" can't be detected by emptiness alone:
        # treat the localhost default as misconfigured in production too (spec 57 §5.6).
        if not self.redis_url or self.redis_url == "redis://localhost:6379/0":
            missing.append("REDIS_URL")
        if missing:
            raise ValueError(f"required in production but unset: {', '.join(missing)}")
        return self

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
