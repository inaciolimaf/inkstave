# ADR 0052 — Security hardening

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context spec:** 52 — Security Hardening (Phase 7)

## Context

Cross-cutting hardening over the whole backend: rate limiting, strict input
validation, CORS, secure headers, upload sanitization, secret guards, a compile-
sandbox review, and a dependency-audit gate. Builds on spec-51's middleware chain.

## Decisions

### 1. Middleware order

Outermost → inner: `RequestContextMiddleware` (51) → `SecurityHeadersMiddleware` →
`BodySizeLimitMiddleware` → `CORSMiddleware` → routing → per-route `rate_limit`
dependency → auth → handler. Headers and the body cap therefore apply to **every**
response, including 404s and error envelopes (asserted by tests).

### 2. Rate limiting — named policies, atomic, fail-open

`inkstave.security.rate_limit` adds a fixed-window limiter incremented with a Lua
script (`INCR`+`EXPIRE`+`TTL` in one round trip — no race). Backends without
server-side scripting (fakeredis in tests) fall back to a two-step INCR/EXPIRE.
Named per-user policies (`compile`, `agent`, `upload`) are FastAPI dependencies on
their routes; the spec-08 auth limiter keeps login/register/refresh. Every limited
response carries `X-RateLimit-Limit/Remaining/Reset`; a 429 adds `Retry-After` +
`X-RateLimit-Remaining: 0`. On a Redis error the limiter **fails open** (logs
`rate_limit_backend_unavailable`, increments `inkstave_rate_limit_errors_total`) so
an outage never locks everyone out. The agent route composes with spec-49's cost cap.

### 3. Strict input validation + body cap

`StrictModel` (`extra="forbid"`, whitespace-stripping) is the request-body base;
unknown fields → 422. `BodySizeLimitMiddleware` rejects oversize bodies with 413
from the `Content-Length` header (and counts streamed bytes) before the handler runs;
upload routes use the larger upload cap. Path/query params stay typed (UUID, bounded).

### 4. CORS + secure headers + secret guard

CORS is an explicit allow-list (`CORS_ORIGINS`); `*` with credentials is a boot-time
error, and an empty list in `production` is rejected (no silent wildcard).
`SecurityHeadersMiddleware` sets CSP, `X-Frame-Options: DENY`, `nosniff`,
`Referrer-Policy`, `Permissions-Policy`, COOP/CORP, HSTS (only when `HSTS_ENABLED`),
and strips `Server`/`X-Powered-By`. A `model_validator` refuses to boot in
`production` with a missing/weak/default `JWT_SECRET` (< 32 bytes or a known default).

### 5. Upload sanitization

`sanitize_filename` strips directory components (`../`, absolute, backslash, NUL),
leading dots, and unsafe chars, capping length — the safe basename is what's stored.
The service enforces an **extension allow-list**, magic-byte content sniffing, and an
**extension↔content match** (a `.png` whose bytes are a PDF → 415), plus the streamed
size cap (413).

### 6. Compile sandbox review (+ one minimal fix)

Tectonic has no shell-escape, so `\write18` is disabled by design; a per-compile
workdir + CPU timeout + output cap come from spec 21. **Gap found & fixed:** the
runner previously passed the full `os.environ` to the compile subprocess, leaking
application secrets to LaTeX. It now builds a minimal allow-listed env
(`PATH/HOME/LANG/LC_ALL/TMPDIR` + `TECTONIC_CACHE_DIR`). The **trusted-users CE
caveat** is documented (`docs/security-checklist.md`, README).

### 7. Dependency audit

`scripts/audit.sh` runs `pip-audit` (backend) + `npm audit --audit-level=high`
(frontend), failing on high/critical not in `scripts/audit-allowlist.txt`. The real
network audit runs in CI (spec 57); the fast suite only asserts the gate exists.

## Consequences

- New `inkstave.security` package (headers, body_limit, rate_limit, uploads) +
  `StrictModel` + config guards + the `inkstave_rate_limit_errors_total` metric.
  `RateLimitError` now carries `X-RateLimit-*`. Filename handling changed from
  reject-invalid to sanitize (documented; one file test updated).
- 17 tests (units + integration) across limiter math/keying/fail-open, headers on
  200/404, 413, 422-extra, 429+headers, CORS preflight, upload mismatch/traversal,
  the compile-sandbox env/flag assertions, and the secret/CORS boot guards.
- Suite stays under 2 minutes; all Redis faked, caps tiny, no network/LLM/Tectonic.
