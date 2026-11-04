# Security

The HTTP and operational hardening shared by every domain: response headers, CORS, body and upload
limits, the rate limiters, client IP resolution, secret handling, deadlines, the dependency audit
and what the nginx proxy does. Identity and sessions are in [auth.md](auth.md); the LaTeX sandbox is
in [compile.md](compile.md); agent safety is in [agent.md](agent.md). Specs 52, 55, 91.

## Where it is

| File | Role |
|---|---|
| `backend/src/inkstave/core/http` | HTTP hardening package |
| `backend/src/inkstave/core/http/headers.py` | `SecurityHeadersMiddleware` |
| `backend/src/inkstave/core/http/body_limit.py` | `BodySizeLimitMiddleware` |
| `backend/src/inkstave/core/http/sse.py` | Shared SSE plumbing (`Keepalive`, `event_pump`), not a security control |
| `backend/src/inkstave/core/http/middleware.py` | Legacy request-id middleware, not wired in |
| `backend/src/inkstave/core/config/settings.py` | Boot guards |
| `backend/src/inkstave/modules/auth/throttling/limiter.py` | `client_ip`, scope limiter, `hit_window` |
| `backend/src/inkstave/modules/auth/throttling/policies.py` | Named-policy limiter with `X-RateLimit-*` |
| `backend/src/inkstave/modules/auth/throttling/login_attempts.py` | `LoginThrottle` |
| `backend/src/inkstave/modules/git/auth/access.py` | Git token authentication and its failure limiter (spec 121) |
| `backend/src/inkstave/modules/git/auth/tokens.py` | Git access tokens: format, SHA-256 storage, `authenticate` |
| `backend/src/inkstave/modules/admin/provisioning/config_check.py` | `validate_config` for `check-config` and `doctor` |
| `backend/src/inkstave/modules/projects/content/files.py` | Upload validation |
| `scripts/audit.sh`, `scripts/audit-allowlist.txt` | Dependency audit |
| `infra/nginx/default.conf`, `infra/nginx/nginx.conf` | Reverse proxy |
| `backend/tests/integration/test_security_api.py` | The HTTP surface |
| `backend/tests/unit/test_production_secrets.py` | Secret guards |

## How it works

### Threat boundaries

Users of one instance are assumed mutually untrusted only with `COMPILE_RUNNER=sandbox`; the default
`local` runner is for users who trust each other ([compile.md](compile.md)). Everything else below
applies in both modes. Only nginx is meant to be reachable; backend and worker sit on the compose
network with no published port.

### Security headers

`SecurityHeadersMiddleware` runs on every HTTP response that passes through it, including 404 and 413.

| Header | Value |
|---|---|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Cross-Origin-Resource-Policy` | `same-origin` |
| `Content-Security-Policy` | `CSP_POLICY` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains`, only with `HSTS_ENABLED=true` |

It also deletes `X-Powered-By` and `Server`.

### CORS

`CORSMiddleware` allows `CORS_ALLOWED_ORIGINS` with credentials. Methods and headers are explicit
lists, deliberately stricter than spec 02: `GET POST PUT PATCH DELETE OPTIONS`, and `Authorization`,
`Content-Type` and the request-id header. It exposes the request-id header,
`X-RateLimit-Remaining` and `Retry-After`. A wildcard is refused in every environment. Under the
nginx deployment the SPA is same-origin, so CORS matters only for a split-origin setup.

### Body and upload limits

Several layers, outermost first.

| Layer | Limit | Default | Response |
|---|---|---|---|
| nginx, `location /api/` | `client_max_body_size` | 50 MiB | nginx 413 |
| `BodySizeLimitMiddleware`, path ending `/files`, `/import` or `/git-upload-pack` | `MAX_UPLOAD_BYTES` | 50 MiB | 413 `{"error":{"code":"payload_too_large",...}}` |
| `BodySizeLimitMiddleware`, path ending `/git-receive-pack` | `GIT_MAX_PUSH_BYTES` | 50 MiB | same (spec 121; nginx's `client_max_body_size` must be at least this) |
| `BodySizeLimitMiddleware`, any other path | `MAX_REQUEST_BODY_BYTES` | 1 MiB | same |
| File upload, streaming | `MAX_UPLOAD_BYTES` | 50 MiB | 413 `file_too_large` |
| Project import, streaming | `IMPORT_MAX_ZIP_BYTES` | 50 MiB | see [projects.md](projects.md) |
| Document replace | `MAX_DOCUMENT_BYTES` | 2,000,000 bytes | see [documents.md](documents.md) |
| Collab frame | `COLLAB_WS_MAX_FRAME_BYTES` | 1 MiB | see [collab.md](collab.md) |

The middleware rejects a declared `Content-Length` over the cap before the route runs. It also
counts received bytes, for a chunked or under-declared body, and turns the route's response into a
413.

Uploads then check the MIME type against `ALLOWED_UPLOAD_MIME`, the extension against
`UPLOAD_ALLOWED_EXTENSIONS`, and that content matches the extension. `StrictModel` rejects unknown
JSON fields with 422.

### Rate limiting

Three mechanisms, all fixed-window counters in Redis, all bypassed by `RATE_LIMIT_ENABLED=false`.
All fail open: a limiter outage allows the request.

| Mechanism | Redis key | Identity | Applied to | Outage signal |
|---|---|---|---|---|
| `limiter.rate_limit(scope)` | `ratelimit:<scope>:<id>` | IP, or IP plus e-mail for `register`, `verify_email`, `magic_link` | Auth routes | warning |
| `policies.rate_limit_named(name)` | `rl:<name>:<id>` | user, else IP | `compile`, `compile_daily`, `agent`, `upload` | warning and `inkstave_rate_limit_errors` |
| `LoginThrottle` | `ratelimit:login:ip:<ip>`, `ratelimit:login:email:<email>` | IP and e-mail, wrong passwords only | Login | warning and metric |
| `git.access` | `rl:git_auth:<ip>` | IP, failed Git token attempts only | Git Smart HTTP routes (spec 121) | none: see below |

The change-password limit is a fourth call site in `backend/src/inkstave/modules/auth/routes/users.py`.
It uses `check_rate_limit` directly. Details of the auth limits are in [auth.md](auth.md). The agent
has further per-user and per-project budgets in [agent.md](agent.md).

A blocked request gets 429 `rate_limited` with `Retry-After`.

The Git token limiter is the exception to fail-open: it does not catch Redis errors, so a Redis outage
answers Git requests with 500. The check runs before anything is written, so nothing changes.

### Git access tokens

A personal access token (`ink_` plus URL-safe random characters, spec 121) authenticates Git's HTTP Basic
password on the `/api/v1/git/projects/{id}.git` routes only. The database keeps its SHA-256 hash; the raw value
is shown once. Revocation and expiry take effect at the next request. Session JWTs are refused on the Git routes,
and Git tokens are refused everywhere else. Each user holds at most 20 active tokens. Details: [git.md](git.md).

### Client IP resolution

`client_ip()` in `backend/src/inkstave/modules/auth/throttling/limiter.py` is the shared source.

| `TRUST_PROXY_HEADERS` | Result |
|---|---|
| `false` (default) | `request.client.host` |
| `true`, header present | The first comma-separated entry of `TRUSTED_PROXY_HEADER` |
| `true`, header absent | `request.client.host` |

Behind nginx with the flag off, the peer is the nginx container, so every anonymous user shares one
IP. `LoginThrottle` handles this: `_counts_ip` is true only with trusted headers or a globally
routable peer, so the per-IP login limit stands down and the per-e-mail limit remains. The other
IP-keyed limits do not stand down: all anonymous users share one counter. Turn
`TRUST_PROXY_HEADERS=true` on behind any proxy, knowing the spoofing issue under "Points of
attention".

### Secrets and boot refusals

Secrets come from the environment or `.env`; `.env.example` documents every variable. `Settings`
refuses to construct in these cases, which stops the API, the worker and the CLI alike.

| Condition | Environment | Refused because |
|---|---|---|
| `JWT_SECRET` unset | all | required field |
| `JWT_SECRET` under 32 bytes, in the weak list, or `EXAMPLE_JWT_SECRET` | `prod` | forgeable tokens |
| Any `JWT_SECRET_PREVIOUS` entry weak | `prod` | retired secrets still verify |
| `CORS_ALLOWED_ORIGINS` contains `*` | all | credentials are enabled |
| `CORS_ALLOWED_ORIGINS` empty | `prod` | no silent wildcard |
| `DATABASE_URL` unset | `prod` | required connection |
| `REDIS_URL` empty or the localhost default | `prod` | required connection |
| `EMAIL_BACKEND=resend` without `RESEND_API_KEY` | `prod` | explicit choice, key cannot be intentional |

The agent provider key (`ANTHROPIC_API_KEY` by default) is deliberately not a boot refusal, since no setting says a deployment has no
agent. `inkstave check-config` reports it in production unless `LLM_STUB=true`, and also reports
malformed DSNs and `EMAIL_BACKEND=smtp` without `SMTP_HOST`.

`redact` strips secret-named keys from JSON logs ([observability.md](observability.md)). Unhandled
errors return no internals. Image builds exclude secrets, and compose carries no inline secret
values.

### Connection deadlines

Every external call has a bound, so a stuck dependency cannot hold a worker forever.

| Target | Setting | Default | Where |
|---|---|---|---|
| Postgres lock | `DB_LOCK_TIMEOUT_S` | 10 s | Engine `server_settings` |
| Postgres statement | `DB_STATEMENT_TIMEOUT_S` | 30 s | Engine `server_settings` |
| Postgres idle in transaction | `DB_IDLE_IN_TRANSACTION_TIMEOUT_S` | 120 s | Engine `server_settings` |
| Redis connect, socket | `REDIS_CONNECT_TIMEOUT_S`, `REDIS_SOCKET_TIMEOUT_S` | 3 s, 5 s | `create_redis_pool` |
| S3 connect, read | `S3_CONNECT_TIMEOUT_S`, `S3_READ_TIMEOUT_S` | 5 s, 30 s | `client_config` |
| SMTP | `SMTP_TIMEOUT_S` | 30 s | Sender |
| LLM request | `AGENT_REQUEST_TIMEOUT_S` | 120 s | LLM client |

`allow_idle` and `allow_long_statements` raise a Postgres limit for one transaction. See
[overview.md](overview.md). Pub/sub readers must poll below `REDIS_SOCKET_TIMEOUT_S`.

### Dependency audit

`scripts/audit.sh` runs `pip-audit` on the backend, then `npm audit --audit-level=high` on the
frontend. Ids in `scripts/audit-allowlist.txt` become `--ignore-vuln` arguments. It is manual, and
its own header says it does not pass today.

### nginx

Read from `infra/nginx/default.conf`, listening on port 80. TLS is expected in front of it.

| Location | Behaviour |
|---|---|
| `= /healthz` | 200 `ok` from nginx, no upstream |
| `/metrics` (prefix) | 404, no upstream |
| `/api/` | Proxied to the backend. `client_max_body_size 50m`, `proxy_read_timeout 65s`. Includes `/api/setup` and `/api/v1/openapi.json` |
| `/ws/` | Proxied with Upgrade headers, 3600 s timeouts |
| `/assets/` | Static, `expires 4h` |
| `= /index.html` | Static, `Cache-Control: no-cache` |
| `/` | Static, `try_files $uri $uri/ /index.html` |

Only `/api/` and `/ws/` reach the backend. `/health`, `/ready`, `/readyz`, `/docs` and `/redoc`
fall through to the SPA and answer 200 with `index.html`. Both proxied locations set `X-Real-IP`,
`X-Forwarded-For` to `$proxy_add_x_forwarded_for`, and `X-Forwarded-Proto` to `$scheme`.

`infra/nginx/nginx.conf` sets `server_tokens off`, gzip, and maps `.mjs` to a JavaScript type. In
`docker-compose.prod.yml` the frontend has `expose: ["80"]` and no `ports:`, for a managed proxy such
as Coolify. A standalone run needs a `ports:` entry added.

## Rules and guarantees

| Invariant | Test |
|---|---|
| Security headers are on 200 and 404; no banner; no HSTS when off | `backend/tests/integration/test_security_api.py::test_security_headers_present_on_404_and_200` |
| An oversize body gets 413 | `backend/tests/integration/test_security_api.py::test_body_size_limit_returns_413` |
| An oversize upload gets `file_too_large` and leaves nothing behind | `backend/tests/integration/test_files_api_validation.py::test_size_limit` |
| Disallowed MIME is refused | `backend/tests/integration/test_files_api_validation.py::test_disallowed_mime` |
| Content must match the extension | `backend/tests/integration/test_files_api_validation.py::test_upload_content_extension_mismatch_is_415` |
| Unknown JSON fields get 422 | `backend/tests/integration/test_security_api.py::test_extra_field_is_rejected_422` |
| CORS preflight allows the configured origin | `backend/tests/integration/test_security_api.py::test_cors_preflight_allows_configured_origin` |
| Wildcard origin refused; empty refused in prod | `backend/tests/unit/test_security.py::test_cors_guard_rejects_wildcard_and_empty_prod` |
| The forwarded header counts only when trusted | `backend/tests/unit/test_rate_limit.py::test_client_ip_uses_proxy_header_only_when_trusted` |
| Named policy sets headers and answers 429 | `backend/tests/integration/test_security_api.py::test_rate_limit_dependency_sets_headers_and_429s` |
| Limiters fail open | `backend/tests/integration/test_security_api.py::test_rate_limit_fails_open_when_redis_errors`, `backend/tests/unit/test_rate_limit.py::test_limiter_fails_open_when_redis_errors` |
| Behind an untrusted proxy the per-IP login limit stands down | `backend/tests/integration/test_login_attempts.py::test_behind_an_untrusted_proxy_the_ip_limit_stands_down` |
| A public peer is limited without trusted headers | `backend/tests/integration/test_login_attempts.py::test_a_public_peer_is_limited_without_trusted_headers` |
| Weak current and previous secrets refuse to boot in prod | `backend/tests/unit/test_production_secrets.py::test_production_refuses_a_bad_current_secret`, `backend/tests/unit/test_production_secrets.py::test_production_refuses_a_bad_previous_secret` |
| `EXAMPLE_JWT_SECRET` matches `.env.example` | `backend/tests/unit/test_production_secrets.py::test_example_constant_matches_env_example` |
| Resend without a key refuses to boot | `backend/tests/unit/test_production_secrets.py::test_resend_backend_without_a_key_refuses_to_boot` |
| A missing LLM key does not stop the boot | `backend/tests/unit/test_production_secrets.py::test_missing_llm_key_does_not_stop_the_boot` |
| `DATABASE_URL` is required in prod | `backend/tests/unit/test_bootstrap_57.py::test_production_requires_database_url` |
| Redis client carries both timeouts | `backend/tests/unit/test_external_timeouts.py::test_redis_client_carries_both_timeouts` |
| SMTP and S3 have timeouts | `backend/tests/unit/test_external_timeouts.py::test_smtp_send_has_a_timeout`, `backend/tests/unit/test_external_timeouts.py::test_s3_client_gets_explicit_timeouts` |
| Idle limit stays above the slowest call in a request | `backend/tests/unit/test_external_timeouts.py::test_idle_limit_stays_above_the_slowest_call_inside_a_request` |
| Audit script exists and runs both tools (the file only, not a pass) | `backend/tests/unit/test_security.py::test_audit_script_exists_and_runs_both_tools` |
| Only the frontend exposes a port, and publishes none | `backend/tests/unit/test_docker_packaging.py::test_only_frontend_exposes_a_port_under_a_managed_proxy` |
| Compose has no inline secrets | `backend/tests/unit/test_docker_packaging.py::test_no_inline_secret_literals` |
| Secrets stay out of the image context | `backend/tests/unit/test_docker_packaging.py::test_dockerignore_excludes_secrets_tests_caches` |
| nginx routes `/api`, upgrades `/ws`, blocks `/metrics` | `backend/tests/unit/test_docker_packaging.py::test_nginx_api_proxies_to_backend`, `backend/tests/unit/test_docker_packaging.py::test_nginx_ws_upgrade_headers`, `backend/tests/unit/test_docker_packaging.py::test_nginx_blocks_metrics_without_upstream` |

## Settings

| Variable | Default | Effect |
|---|---|---|
| `JWT_SECRET`, `JWT_SECRET_PREVIOUS` | required, empty | See [auth.md](auth.md) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Allow-list; `CORS_ORIGINS` is an alias |
| `HSTS_ENABLED` | `false` | Emit HSTS |
| `CSP_POLICY` | `default-src 'self'; img-src 'self' data:; ...` | CSP on backend responses |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | JSON cap |
| `MAX_UPLOAD_BYTES` | `52428800` | Upload cap |
| `ALLOWED_UPLOAD_MIME`, `UPLOAD_ALLOWED_EXTENSIONS` | see `backend/src/inkstave/core/config/groups.py` | Allow-lists |
| `RATE_LIMIT_ENABLED` | `true` | Master switch for all limiters |
| `RATE_LIMIT_COMPILE`, `RATE_LIMIT_COMPILE_DAILY` | `20/60`, `30/86400` | Per user |
| `RATE_LIMIT_AGENT`, `RATE_LIMIT_UPLOAD` | `30/60`, `60/60` | Per user |
| `RATE_LIMIT_GIT_AUTH` | `20/300` | Failed Git token attempts per IP ([git.md](git.md)) |
| `GIT_ENABLED`, `GIT_MAX_PUSH_BYTES` | `false`, `52428800` | Git access, its push cap ([git.md](git.md)) |
| `TRUST_PROXY_HEADERS` | `false` | Honour the proxy header |
| `TRUSTED_PROXY_HEADER` | `X-Forwarded-For` | Which header |
| `METRICS_PUBLIC` | `true` | See [observability.md](observability.md) |
| `DOCS_ENABLED` | `true` | `/docs`, `/redoc` |

## Points of attention

- **`X-Forwarded-For` is spoofable with `TRUST_PROXY_HEADERS=true`.** `client_ip` takes the first
  entry. nginx's `$proxy_add_x_forwarded_for` appends to whatever the client sent, so the first entry
  is client-controlled. An attacker rotating that header escapes every IP-keyed limit, including
  the per-IP login limit. `backend/tests/unit/test_rate_limit.py::test_client_ip_uses_proxy_header_only_when_trusted`
  fixes this "first hop" behaviour. The trustworthy entry counts from the right.
- **The change-password limit skips `client_ip`.** `backend/src/inkstave/modules/auth/routes/users.py`
  uses `request.client.host` directly, and its outage path neither logs nor counts.
- **An outer proxy's `X-Forwarded-Proto` is lost.** nginx overwrites it with `$scheme`, always
  `http` on this listener. Nothing in `backend/src` reads the scheme today, and no route sets a
  cookie, so this has no effect yet. Anything that starts reading it would see `http` behind TLS.
- **The backend command has no `--proxy-headers`.** `docker-compose.prod.yml` and `backend/Dockerfile`
  run plain `uvicorn`. Uvicorn defaults to `proxy_headers=True` with `forwarded_allow_ips` of
  `127.0.0.1`, or the `FORWARDED_ALLOW_IPS` variable. nginx connects from another container, so
  `request.client.host` stays nginx's address. `client_ip` is the only thing that recovers the real
  IP.
- **The SPA document carries none of nginx's security headers.** nginx inherits `add_header` only
  when the location defines none. `location = /index.html` and `location = /healthz` define their
  own, so `X-Frame-Options`, `X-Content-Type-Options` and `Referrer-Policy` are dropped, and every
  client route resolves to `index.html`. Static files under `/assets/` keep them. Derived from the
  config and nginx's documented inheritance rule, not run.
- **The SPA has no CSP at all.** The header is a comment in `infra/nginx/default.conf`. `CSP_POLICY`
  applies only to backend responses, which are JSON.
- **HSTS is off by default**, and nothing in the guards forces it on in production.
- **The middleware's 413 is not the envelope.** It answers `{"error":{"code":"payload_too_large",...}}`:
  `code`, not `type`, and no `request_id`. A client parsing `error.type` gets nothing. No test
  asserts the shape.
- **Documents cap at 1 MiB, not 2 MB.** `PUT /api/v1/projects/{project_id}/documents/{entity_id}` is a
  JSON route, so `MAX_REQUEST_BODY_BYTES` rejects it well before `MAX_DOCUMENT_BYTES` applies.
- **Raising an import limit needs three changes.** `IMPORT_MAX_ZIP_BYTES` above 50 MiB also needs
  `MAX_UPLOAD_BYTES` and nginx's `client_max_body_size` raised, the latter in the image.
- **`_UPLOAD_SUFFIXES` is a path suffix match**, so any route ending in `/files` or `/import` gets the
  50 MiB cap. All such routes today are the upload and import ones.
- **A 500 carries no security headers.** It leaves through `ServerErrorMiddleware`, outside
  `SecurityHeadersMiddleware` and `CORSMiddleware`. A cross-origin client sees a CORS failure instead
  of the status. See [observability.md](observability.md).
- **`doctor` prints the database password.** `_cmd_doctor` uses `settings.database_url` as the probe
  label, in full, on stdout or stderr.
- **`/docs` and `/redoc` default to on.** nginx does not route them, but port 8000 does, and
  `/api/v1/openapi.json` is public through `/api/`.
- **The audit is not in CI.** `.github/workflows/ci.yml` does not call `scripts/audit.sh`, and the
  allowlist has no entries, only its format comment. `pip-audit` on the locked runtime dependencies,
  run 2026-10-30, reports 41 advisories in 12 packages, led by `pyjwt` (15) and `aiohttp` (11), with
  `urllib3`, `starlette`, `anyio` and `langgraph-sdk` among the rest. `set -e` then stops the script
  before the frontend step, which would fail regardless: `npm audit` needs a `package-lock.json`,
  and this is a pnpm project. Expiry dates in the allowlist format are not enforced by the script.
- **`PUBLIC_HTTP_PORT` does nothing.** `.env.example`, `README.md`, `docs/admin-guide.md` and
  `docs/release-checklist.md` describe it. No compose file reads it, and `docker-compose.prod.yml`
  publishes no port.
- **Rate-limit windows are fixed.** A burst across a boundary can reach twice the limit. The Lua
  script exists twice, in `limiter.py` and `policies.py`.
- **The login limit behind a proxy is weaker without trusted headers.** Stand-down is the safer
  failure, but distributed guessing against many e-mails is then limited only per address.
