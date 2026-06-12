"""Field-group mixins for :class:`inkstave.config.Settings`.

This module exists purely to keep ``config.py`` under the line budget: the
settings fields are partitioned into cohesive mixin classes by domain/spec, and
``Settings`` composes them via multiple inheritance. Pydantic v2 collects fields
across the MRO, so field names, defaults, validation aliases and env-var
behaviour are identical to a single flat class — only the source layout changes.

Mixins are plain annotated classes (not ``BaseModel``); pydantic-settings reads
their annotations through ``Settings``'s MRO. Validators stay in
``config.py`` so all guards remain in one place.

Ordering note: pydantic builds fields base-classes-first along the MRO, so the
mixin list order in ``Settings`` defines the field order. The groups below are
listed in their original top-to-bottom order to preserve it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import NoDecode


class CoreSettingsMixin:
    """App identity, logging, CORS, Redis/DB URLs and request plumbing."""

    app_name: str = "Inkstave"
    environment: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    docs_enabled: bool = True

    # ``NoDecode`` stops pydantic-settings from JSON-decoding the raw env value
    # so the validator below can accept a plain comma-separated string too.
    # Spec 52 §5.8 names this ``CORS_ALLOWED_ORIGINS``; the legacy ``CORS_ORIGINS``
    # name is still accepted for back-compat (spec 68 #219).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"],
        validation_alias=AliasChoices("cors_allowed_origins", "cors_origins"),
    )

    redis_url: str = "redis://localhost:6379/0"
    # Reserved for spec 03 (database layer): read but unused here. Optional so
    # the app never fails to construct when it is absent (e.g. in tests).
    database_url: str | None = None

    # Deploy (spec 57): in strict mode (default) the app refuses to start unless
    # the DB is at Alembic head — migrations run via the one-shot `migrate` step.
    # Set true for single-node/dev convenience to migrate at startup instead.
    migrate_on_start: bool = False

    request_id_header: str = "X-Request-ID"

    # --- Performance: DB pool + hot-read cache (spec 53) ---
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    cache_enabled: bool = True
    cache_ttl_seconds: int = 30

    # --- Observability (spec 51) ---
    log_format: Literal["json", "console"] = "json"
    log_stacks: bool = True
    service_name: str = "inkstave-backend"
    app_version: str = "0.0.0"
    git_sha: str = "unknown"
    metrics_public: bool = True
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "inkstave-backend"
    readiness_check_timeout_s: float = 2.0


class AuthSettingsMixin:
    """Argon2id hashing, JWT auth and rate limiting (specs 06–08, 52)."""

    # Argon2id password-hashing parameters (spec 06). Defaults match argon2-cffi;
    # tests lower these so hashing is sub-millisecond and the suite stays fast.
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4

    # JWT authentication (spec 07). jwt_secret is required (no default) so the
    # app fails fast if it is unset. jwt_secret_previous holds retired secrets
    # accepted for verification only, enabling zero-downtime secret rotation.
    jwt_secret: str
    jwt_secret_previous: Annotated[list[str], NoDecode] = Field(default_factory=list)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "inkstave"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 1209600

    # Rate limiting (spec 08). Values are "<limit>/<window_seconds>". The limiter
    # fails open if Redis is unavailable.
    rate_limit_enabled: bool = True
    # Spec 52 §5.8 names this ``RATE_LIMIT_AUTH_LOGIN``; the legacy ``RATE_LIMIT_LOGIN``
    # name is still accepted for back-compat (spec 68 #219).
    rate_limit_login: str = Field(
        default="10/300",
        validation_alias=AliasChoices("rate_limit_auth_login", "rate_limit_login"),
    )
    rate_limit_register: str = "5/3600"
    rate_limit_refresh: str = "30/300"
    # Change-password / sensitive auth endpoints (spec 52 §5.2.1): 5/hour, user_or_ip.
    rate_limit_auth_password: str = "5/3600"
    # Per-user policies hardened in spec 52 ("<limit>/<window_seconds>").
    rate_limit_compile: str = "20/60"
    rate_limit_agent: str = "30/60"
    rate_limit_upload: str = "60/60"
    # Header carrying the real client IP behind a trusted proxy.
    trusted_proxy_header: str = "X-Forwarded-For"
    # Only honour the proxy header for client IP when behind a known proxy (spec 52).
    trust_proxy_headers: bool = False


class SecuritySettingsMixin:
    """HTTP security hardening, upload allow-lists and document limits (spec 52)."""

    # --- Security hardening (spec 52) ---
    hsts_enabled: bool = False
    csp_policy: str = (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    max_request_body_bytes: int = 1_048_576  # 1 MiB global JSON cap
    upload_allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".pdf",
            ".bib",
            ".tex",
            ".cls",
            ".sty",
            ".svg",
            ".eps",
            ".csv",
            ".txt",
        ]
    )
    # WebSocket close code for an unauthorized connection (contract for spec 29).
    ws_auth_close_code: int = 4401

    # Max UTF-8 byte length of a single document on replace (spec 13).
    max_document_bytes: int = 2_000_000


class StorageSettingsMixin:
    """Binary file storage: local/S3 backend, upload limits and MIME allow-list (spec 14)."""

    file_storage_backend: Literal["local", "s3"] = "local"
    file_storage_local_path: str = "./data/files"
    max_upload_bytes: int = 52_428_800  # 50 MB
    allowed_upload_mime: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
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
    )
    storage_stream_chunk_bytes: int = 65_536
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""


class CompileSettingsMixin:
    """Tectonic compilation, output storage/retention and async jobs (specs 21–23)."""

    # LaTeX compilation via Tectonic (spec 21).
    # ``compile_mode`` selects the runner: "real" runs the Tectonic binary; "mock"
    # (e2e/test only, spec 54) swaps in a deterministic runner that emits a tiny
    # canned PDF + log with no subprocess. Production defaults to "real".
    compile_mode: Literal["real", "mock"] = "real"
    # ``llm_stub`` (e2e/test only, spec 54) swaps the agent's LLM client for a
    # deterministic, network-free stub that scripts a search → read → propose_edit
    # tool sequence and a fixed reply. Production defaults to False (real provider).
    llm_stub: bool = False
    tectonic_bin: str = "tectonic"
    tectonic_cache_dir: str = "/var/cache/tectonic"
    tectonic_bundle_url: str = ""
    tectonic_offline: bool = False
    compile_workdir_root: str = "/tmp/inkstave-compiles"
    tectonic_compile_timeout_s: int = 60
    compile_max_input_files: int = 2000
    compile_max_input_bytes: int = 104_857_600  # 100 MiB
    # Safety cap on tree nodes materialised per read (spec 99); generous so normal
    # projects are unaffected. get_tree raises TreeTooLargeError past it.
    tree_max_nodes: int = 50_000
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


class ImportSettingsMixin:
    """Project import from a ``.zip`` archive — bounds + allow-list (spec 101).

    Defaults are safe and keep tests cheap; the unzip work is bounded entirely by
    these limits (zip-bomb defence) before any byte is decompressed.
    """

    import_max_zip_bytes: int = 52_428_800  # 50 MiB — max compressed upload (streamed guard)
    import_max_uncompressed_bytes: int = 314_572_800  # 300 MiB — max total kept uncompressed
    import_max_file_bytes: int = 52_428_800  # 50 MiB — max uncompressed size of any one entry
    import_max_entries: int = 2_000  # max kept (folders+docs+files) entries
    import_allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            ".tex",
            ".bib",
            ".cls",
            ".sty",
            ".bst",
            ".bbx",
            ".cbx",
            ".txt",
            ".md",
            ".csv",
            ".tsv",
            ".json",
            ".yml",
            ".yaml",
            ".xml",
            ".svg",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".pdf",
            ".eps",
        ]
    )
    import_workdir_root: str = "/tmp/inkstave-imports"  # scratch dir for the bounded temp copy


class ExportSettingsMixin:
    """Project export as a ``.zip`` — size cap + async toggle (spec 102).

    The stream chunk size reuses ``storage_stream_chunk_bytes`` (no separate knob).
    """

    export_max_total_bytes: int = 209_715_200  # 200 MiB — sum of doc + file bytes (sync path)
    export_async_enabled: bool = False  # over-threshold → ARQ artifact instead of 413 (optional)


class CollabSettingsMixin:
    """SyncTeX, log parsing, CRDT document model and the collab WebSocket (specs 26–29)."""

    # SyncTeX source <-> PDF sync (spec 26).
    synctex_max_gz_bytes: int = 33_554_432  # 32 MiB; larger files are refused
    synctex_index_cache_size: int = 16  # parsed indices kept in process (0 disables)

    # LaTeX log -> structured problems parsing (spec 27).
    logparse_max_log_bytes: int = 8_388_608  # 8 MiB; larger logs are tail-truncated
    logparse_wrap_width: int = 79  # TeX log hard-wrap width for de-wrapping
    logparse_max_problems: int = 1000  # cap on returned problems

    # Server-side CRDT document model (spec 28).
    collab_snapshot_every_updates: int = 200  # compact after this many appended updates
    collab_snapshot_interval_seconds: float = 30.0  # or after this long since last snapshot
    collab_text_flush_debounce_ms: int = 1000  # debounce for the spec-13 text bridge
    collab_idle_evict_seconds: float = 300.0  # evict idle in-memory docs after this
    collab_max_update_bytes: int = 1_048_576  # reject a single update larger than this (1 MiB)

    # Collaboration WebSocket transport (spec 29).
    collab_ws_max_frame_bytes: int = 1_048_576  # max inbound WS frame size
    collab_ws_send_queue_max: int = 256  # bounded per-connection send buffer
    collab_ws_slow_client_timeout_ms: int = 2000  # slow-consumer enqueue timeout
    collab_ws_max_msgs_per_sec: int = 200  # inbound rate guard per connection
    collab_ws_ping_interval_seconds: float = 25.0  # (delegated to the ASGI server)
    collab_ws_pong_timeout_seconds: float = 10.0  # (delegated to the ASGI server)
    collab_redis_channel_prefix: str = "collab:doc:"  # one pub/sub channel per document


class CollaborationSettingsMixin:
    """Sharing/invites, access control, version history and notifications (specs 33–39)."""

    # Collaborators & sharing (spec 33).
    frontend_url: str = "http://localhost:5173"  # base for invite accept links
    invite_ttl_days: int = 14  # pending invite lifetime
    email_change_token_ttl: int = 86400  # email-change confirmation token lifetime (spec 59)

    # Access control (spec 34).
    compile_allowed_for_viewers: bool = True  # viewers may trigger/read compiles

    # Version-history capture (spec 36).
    history_capture_enabled: bool = True  # observe the CRDT stream into version history
    history_debounce_ms: int = 5000  # idle debounce before flushing buffered updates
    history_flush_max_buffer: int = 200  # raw updates buffered before a forced flush
    history_chunk_max_updates: int = 100  # captured updates per chunk before sealing
    history_inline_max_bytes: int = 65536  # payloads above this are offloaded to blob storage
    history_compact_min_updates: int = 50  # min updates before the sweep compacts a doc
    history_compact_merge_bytes: int = 4096  # adjacent updates smaller than this may be merged
    history_compact_interval_s: int = 300  # compaction sweep interval (mocked in tests)
    history_blob_prefix: str = "history/"  # blob-storage key prefix for offloaded payloads

    # History API (spec 37).
    history_diff_max_bytes: int = 2_097_152  # max reconstructed text per side before 413
    history_versions_page_max: int = 200  # upper bound for the versions list `limit`

    # Email + notifications (spec 39).
    email_backend: Literal["smtp", "console", "file"] = "console"
    email_from: str = "Inkstave <no-reply@inkstave.local>"
    email_file_dir: str = "./tmp/emails"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    app_base_url: str = "http://localhost"  # base for accept_url / reset_url in emails
    notification_invite_ttl_days: int = 30
    notification_sweep_interval_s: int = 3600  # expiry sweep interval (mocked in tests)
