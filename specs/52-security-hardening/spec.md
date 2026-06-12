# Spec 52 — Security Hardening (requirements)

## 1. Summary

This spec applies cross-cutting security hardening to the whole backend:
**Redis-backed rate limiting** on authentication, compile, agent and upload
endpoints; **strict input validation** (Pydantic v2 everywhere, including limits
and forbidden-extra); a **CORS allow-list**; **secure response headers** (CSP,
HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
`Permissions-Policy`); **secret-management & rotation guidance**; **upload
sanitization** (size/type/filename limits); a **review of the LaTeX compile
sandbox** that reaffirms the trusted-users Community-Edition caveat and the
spec-21 isolation; and a **dependency/audit-scanning** gate. It ships a concrete
**security checklist** used as the review gate.

## 2. Context & dependencies

- **Depends on:** spec **08** (auth guards, sessions, `get_current_user`,
  logout — the auth limiter wraps login/refresh/register; the middleware chain
  sits around these), spec **34** (access-control enforcement across REST, WS and
  compile — reinforced and tested here, not re-implemented), spec **49** (agent
  rate limits and cost controls — folded into the unified limiter).
- **Builds on:** spec **51** (request-context middleware ordering; security
  middleware runs just inside it). Spec **14** (binary upload storage) and spec
  **21** (Tectonic sandbox/isolation) provide the surfaces hardened here.
- **Unlocks:** spec **53** (perf gate runs the audit too), spec **54** (e2e
  asserts headers/limits hold), spec **56/57** (Docker/CI run the dependency
  audit and set secrets/headers in prod).
- **Affected areas:** backend (middleware, limiter, validation, uploads, compile
  invocation guard), infra (`.env.example`, CI audit step note), docs (security
  ADR + checklist).

## 3. Goals

- A reusable **rate limiter** (`app/security/rate_limit.py`) backed by Redis,
  applied as a FastAPI dependency with named policies for auth, compile, agent
  and upload routes (§5.2.1). Fails **closed for auth** is *not* required, but
  fails **open with a logged warning** when Redis is unavailable is the chosen
  default (documented), so an outage doesn't lock everyone out.
- **Strict validation** conventions enforced project-wide (§5.2.2): every request
  body is a Pydantic model with `extra="forbid"`, bounded string lengths,
  bounded collection sizes, and a global request-body size limit middleware.
- A **CORS allow-list** driven by config (no wildcard with credentials) (§5.2.3).
- A **secure-headers middleware** adding CSP, HSTS, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, and
  `Cross-Origin-*` headers (§5.2.4).
- **Upload sanitization** for binary files: extension allow-list, MIME sniffing,
  per-file and per-request size caps, filename normalization (§5.2.5).
- A **compile-sandbox review** that reaffirms the CE trusted-users caveat and
  asserts the spec-21 resource limits are applied (§5.4).
- **Secret-management & rotation guidance** documented; a startup check that
  refuses to boot in `production` with default/weak secrets (§5.5).
- A **dependency-audit** command (`pip-audit` + `npm audit`) wired as a CI step,
  failing on high/critical (§5.6).
- A written **security checklist** (§5.7) that doubles as the review gate.

## 4. Non-goals (explicitly out of scope)

- Re-implementing authentication or authorization (specs 07/08/34 own those; this
  spec only reinforces and adds adversarial tests for known gaps).
- A true multi-tenant compile sandbox / per-user container isolation beyond the
  Community-Edition trusted-users model. We **reaffirm the caveat** and apply
  process/resource limits from spec 21; full isolation (gVisor/Server-Pro-style
  sandboxed compiles) is explicitly out of scope and documented as such.
- WAF, DDoS protection, TLS termination (operator/nginx concern, spec 56).
- Pen-test engagement, bug-bounty, SOC2 — process, not code.
- Secret-vault integration (HashiCorp Vault, KMS). We document rotation and read
  secrets from env; integrating a vault is future work.
- CSRF tokens: Inkstave uses **bearer JWTs in the `Authorization` header** (spec
  07), not cookies for API auth, so classic CSRF does not apply to the API; if
  any cookie-based flow exists it must be `SameSite=Lax`/`Strict` + `Secure` +
  `HttpOnly` (documented), but token-based CSRF middleware is out of scope.

## 5. Detailed requirements

### 5.1 Middleware ordering

From outermost to innermost: `RequestContextMiddleware` (spec 51) →
`SecurityHeadersMiddleware` → `BodySizeLimitMiddleware` → `CORSMiddleware`
(Starlette) → routing → per-route `RateLimit` dependency → auth dependency →
handler. Document this order in the ADR; tests assert headers appear even on
error/404 responses (i.e. the headers middleware is outer enough).

### 5.2 Backend / API

#### 5.2.1 Rate limiting

Implement a token-bucket or fixed/sliding-window limiter over Redis. Use a single
atomic operation per check — a **Lua script** (`INCR`+`EXPIRE` window, or a
sliding window with a sorted set) executed via `EVALSHA` — to avoid race
conditions. Provide:

```python
class RateLimitPolicy(BaseModel):
    name: str
    limit: int          # requests
    window_seconds: int # per window
    key: Literal["ip", "user", "user_or_ip"]

def rate_limit(policy: RateLimitPolicy) -> Callable:  # FastAPI dependency factory
    ...
```

The **key** is derived as `f"rl:{policy.name}:{scope}"` where `scope` is the
client IP (from a trusted proxy header only if `TRUST_PROXY_HEADERS=true`, else
`request.client.host`), the user id, or whichever is available. On limit
exceeded: return **`429 Too Many Requests`** with the project's standard error
envelope and a `Retry-After` header (seconds until window reset) and an
`X-RateLimit-Remaining: 0` header. On Redis error: **fail open**, log a `warning`
(`rate_limit_backend_unavailable`), and increment a counter
`inkstave_rate_limit_errors_total` (reuse spec 51 metrics).

Default policies (overridable via settings):

| Policy | Applies to | Default | Key |
| --- | --- | --- | --- |
| `auth_login` | `POST /auth/login`, `/auth/refresh` | 10 / 5 min | `ip` (and `user_or_ip` on login) |
| `auth_register` | `POST /auth/register` | 5 / hour | `ip` |
| `auth_password` | password-change/reset endpoints if present | 5 / hour | `user_or_ip` |
| `compile` | `POST /projects/{id}/compile` | 20 / min | `user` |
| `agent` | agent chat/run endpoints | 30 / min **and** the cost cap from spec 49 | `user` |
| `upload` | `POST .../files` (binary upload) | 60 / min | `user` |

Successful auth limiter additionally resets the per-account counter on success
where it makes sense (document; optional). Agent limiting composes with spec 49's
token/cost ceiling — both must pass.

Provide standard headers on **all** rate-limited responses (not only 429):
`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (unix seconds).

#### 5.2.2 Input validation

- Every endpoint accepting a body uses a Pydantic v2 model with
  `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected
  (`422`). Provide a shared base `StrictModel` to enforce this once.
- Enforce **bounded** `max_length` on all free-text string fields (e.g. names
  ≤ 255, messages ≤ a documented cap), and bounded sizes on lists (e.g. batch
  endpoints).
- **Global body-size limit middleware** (`BodySizeLimitMiddleware`): reject
  requests whose `Content-Length` exceeds `MAX_REQUEST_BODY_BYTES` with `413
  Payload Too Large` before reading the body; also guard streamed bodies without
  a length by counting bytes and aborting past the cap. Upload routes use the
  larger `MAX_UPLOAD_BYTES` (§5.2.5) instead.
- Path/query params: use FastAPI typed params with constraints (`Path(...,
  ge=...)`, UUID types) so malformed ids return `422`, not `500`.
- Reaffirm that user-supplied content rendered anywhere (agent chat echoes, file
  names in the UI) is treated as data; the API never reflects raw input into HTML
  (frontend escapes — note for spec 09/46 already done; here just assert API
  returns JSON, never HTML built from input).

#### 5.2.3 CORS

Use Starlette's `CORSMiddleware` configured from `CORS_ALLOWED_ORIGINS` (a
comma-separated allow-list). Rules: **never** `allow_origins=["*"]` together with
`allow_credentials=True`; if credentials are needed, origins must be explicit.
Allow only the methods the API uses and the headers it needs
(`Authorization`, `Content-Type`, `X-Request-ID`). Default in dev:
`http://localhost:5173`; in prod the operator sets the real origin(s). An empty
allow-list in `production` is a boot-time error (no silent wildcard).

#### 5.2.4 Secure headers

`SecurityHeadersMiddleware` sets on every response (configurable, with sane
defaults):

| Header | Default value | Notes |
| --- | --- | --- |
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` | API responses are JSON; the SPA's CSP (with PDF.js/worker needs) is documented and may relax `worker-src`/`blob:` as required — keep it tight, document any relaxation |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | **only when `HSTS_ENABLED=true`** (off in dev/test to avoid pinning localhost) |
| `X-Frame-Options` | `DENY` | clickjacking |
| `X-Content-Type-Options` | `nosniff` | |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | minimal |
| `Cross-Origin-Opener-Policy` | `same-origin` | |
| `Cross-Origin-Resource-Policy` | `same-origin` | |
| `X-Powered-By` / server banner | **removed** | don't advertise framework/version |

PDF served from the output endpoint (spec 23) must set `Content-Type:
application/pdf`, `X-Content-Type-Options: nosniff`, and a `Content-Disposition`;
review that user-controlled filenames in `Content-Disposition` are sanitized.

#### 5.2.5 Upload sanitization

Harden the binary-upload path (spec 14):

- **Size:** per-file cap `MAX_UPLOAD_BYTES` (default 50 MiB) enforced while
  streaming (abort + `413` past the cap, don't buffer the whole file first).
- **Type:** an **extension allow-list** (e.g. `.png .jpg .jpeg .gif .pdf .bib
  .tex .cls .sty .svg .eps .csv .txt` — final list documented) **and** a content
  sniff (magic bytes via `python-magic`/`filetype`, or a lightweight signature
  check) so a `.png` that isn't really a PNG is rejected. Mismatch → `415
  Unsupported Media Type`.
- **Filename:** normalize — strip directory components (no `../`, no absolute
  paths, no NUL), restrict to a safe charset, cap length, de-duplicate. The
  sanitized name is what's stored; reject path traversal outright.
- **Count:** bound files-per-request and total project file count if not already.
- SVG/EPS are accepted as binary assets but are **never** rendered as HTML by the
  backend (note: SVG can carry scripts — the frontend must render them as images
  or sanitize; document this risk in the checklist).

#### 5.2.6 Reinforced authz tests (spec 34)

Add adversarial integration tests (no new code unless a gap is found): a
non-member cannot read/write a project's files, cannot compile it, cannot open
its collab WS, cannot run the agent on it; a `viewer` cannot mutate; IDOR attempts
(guessing another project's UUID) return `403`/`404` consistently (don't leak
existence). If a real gap is found, fix it minimally and note it in the changelog
(this is allowed since the spec's job is hardening).

### 5.3 Frontend / UI

None beyond documenting the SPA CSP needs (PDF.js worker, blob URLs) for spec 56
to apply at the nginx/static layer. No UI work in this spec.

### 5.4 Compile sandbox review

- **Reaffirm the caveat (verbatim intent, your own words):** Inkstave Community
  Edition runs LaTeX compiles in an environment where **all users of an instance
  are trusted**. Without per-user sandboxing, a compile can read/write the
  compile container's filesystem, network and env. This is the same posture as
  Overleaf CE and **must** be stated in `docs/` and the README's security note.
- **Assert spec-21 isolation is in force:** compiles run via Tectonic with
  `--untrusted`-style restrictions where available, in a dedicated working
  directory per compile that is cleaned up, with `\write18`/shell-escape
  **disabled**, a CPU **timeout**, a memory/output-size cap, and no inherited
  secrets in the compile environment. This spec adds tests that these limits are
  configured (e.g. shell-escape off, timeout set), not new compile code.
- Network egress from the compile step should be disabled/limited (Tectonic may
  fetch packages; document that the package set is pinned per spec 21 and that in
  the hardened/offline mode network is restricted — operator/Docker concern in
  spec 56, referenced here).

### 5.5 Secret management & rotation

- All secrets come from env (`JWT_SECRET`/signing keys, `OPENROUTER_API_KEY`, DB
  and Redis credentials). `.env.example` documents each with placeholder values.
- **Boot-time guard:** in `production`, refuse to start if `JWT_SECRET` (or
  equivalent) is empty, shorter than 32 bytes, or equal to a known default/dev
  value; log a fatal and exit. In dev/test a generated/default secret is allowed.
- **Rotation guidance (docs):** how to rotate `JWT_SECRET` with overlapping
  validity (support a current + previous key for verification during rotation —
  document the approach even if implementing dual-key verification is left to
  spec 07's owner; at minimum document the operational steps), how to rotate the
  OpenRouter key, DB/Redis credentials, and that rotating `JWT_SECRET` invalidates
  outstanding tokens.
- Secrets are **never** logged (enforced by spec 51's redaction denylist; add the
  secret env var names to it).

### 5.6 Dependency / audit scanning

- Provide a make/script target `audit` that runs **`pip-audit`** (backend) and
  **`npm audit --audit-level=high`** (frontend) and exits non-zero on
  high/critical advisories.
- Wire it as a CI job (spec 57 owns the CI file; here, define the command and the
  failure threshold; provide an allowlist mechanism for accepted/false-positive
  advisories with a documented expiry).
- Pin dependencies (lockfiles already exist); document the update cadence in the
  checklist.

### 5.7 Security checklist (the review gate)

Author `docs/security-checklist.md` with checkable items, grouped:
**Transport/headers** (HSTS, CSP, frame/nosniff/referrer/permissions, banner
removed) · **AuthN/Z** (JWT secret strength + boot guard, refresh rotation,
authz on every project resource incl. WS & compile, no IDOR/enumeration) ·
**Rate limiting** (auth/compile/agent/upload policies present, 429 + Retry-After,
fail-open documented) · **Input** (Pydantic `extra=forbid`, length/size caps,
body-size middleware, typed path params) · **Uploads** (size/type/sniff/filename)
· **CORS** (explicit allow-list, no `*`+credentials) · **Compile sandbox**
(trusted-users caveat documented, shell-escape off, timeout/limits, temp cleanup)
· **Secrets** (env-only, redacted in logs, rotation doc) · **Dependencies**
(`pip-audit`/`npm audit` green or allowlisted). Each item links to the test or
code proving it. This file is the artifact reviewers tick through.

### 5.8 Configuration

Add to `.env.example`:

| Var | Default | Purpose |
| --- | --- | --- |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | comma-separated allow-list |
| `HSTS_ENABLED` | `false` (`true` in prod) | emit HSTS header |
| `CSP_POLICY` | (the default above) | override CSP if needed |
| `TRUST_PROXY_HEADERS` | `false` | trust `X-Forwarded-For` for client IP (only behind a known proxy) |
| `MAX_REQUEST_BODY_BYTES` | `1048576` (1 MiB) | global JSON body cap |
| `MAX_UPLOAD_BYTES` | `52428800` (50 MiB) | per-file upload cap |
| `UPLOAD_ALLOWED_EXTENSIONS` | (the documented list) | upload extension allow-list |
| `RATE_LIMIT_ENABLED` | `true` (`false` in unit tier if needed) | master switch |
| `RATE_LIMIT_AUTH_LOGIN` | `10/300` | `limit/window_seconds` |
| `RATE_LIMIT_COMPILE` | `20/60` | per-user compile cap |
| `RATE_LIMIT_AGENT` | `30/60` | per-user agent cap |
| `RATE_LIMIT_UPLOAD` | `60/60` | per-user upload cap |

Test profile: `RATE_LIMIT_ENABLED=true` but limits exercised against fakeredis;
`HSTS_ENABLED=false`; small `MAX_*` caps so size tests are cheap.

## 6. Overleaf reference (study only — never copy)

> Read these in `../overleaf/` to understand the approach. Inkstave code must be
> written independently. These are Express/Node; transfer the *concepts* only.

- `services/web/app/src/infrastructure/RateLimiter.mjs` and
  `services/web/app/src/infrastructure/rate-limiters/` — how they model named
  rate-limit policies over Redis and apply them to sensitive routes. Learn the
  policy/keying approach, then write your own Redis limiter.
- `services/web/app/src/infrastructure/CSP.mjs` — how a Content-Security-Policy
  is assembled and what directives they include. Learn the directive set; write
  your own.
- `services/web/app/src/infrastructure/HttpPermissionsPolicy.mjs` — the
  Permissions-Policy approach.
- `services/web/app/src/infrastructure/Validation.mjs` and
  `services/web/app/src/infrastructure/Sanitize.mjs` — their input
  validation/sanitization seams (you'll use Pydantic + your own upload checks).
- `services/web/app/src/infrastructure/JsonWebToken.mjs` — JWT handling concepts
  (secret usage) — relevant to the secret-strength boot guard only.
- **The README "Sandbox Compiles" caveat** (root `README.md`, the blockquote
  stating CE is for environments where **all users are trusted** and that without
  Sandboxed Compiles users have full read/write access to the compile container).
  Reaffirm this caveat for Inkstave in your own words in `docs/`.

## 7. Acceptance criteria

1. **Given** more than `auth_login.limit` login attempts from one IP within the
   window, **then** the next attempt returns `429` with a `Retry-After` header and
   `X-RateLimit-Remaining: 0`, and the limit resets after the window.
2. **Given** Redis is unreachable, **when** a rate-limited endpoint is hit, **then**
   the request is allowed (fail-open), a `warning` is logged, and
   `inkstave_rate_limit_errors_total` increments — the app does not 500.
3. **Given** compile/agent/upload endpoints, **then** each enforces its
   configured per-user policy independently (exceeding one does not affect
   another) and the agent endpoint also honours spec 49's cost cap.
4. **Given** a request body with an unknown extra field, **then** the API returns
   `422` (`extra="forbid"`); a body exceeding `MAX_REQUEST_BODY_BYTES` returns
   `413` before the handler runs.
5. **Given** any response (including 404 and error responses), **then** it carries
   `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, a CSP, a
   Referrer-Policy and a Permissions-Policy, and does **not** carry a framework
   `X-Powered-By`/server banner; HSTS is present only when `HSTS_ENABLED=true`.
6. **Given** `CORS_ALLOWED_ORIGINS` set to one origin, **then** a preflight from an
   allowed origin succeeds with the echoed origin, and a request from a
   non-listed origin is not granted CORS; `*`+credentials is never emitted; an
   empty allow-list in `production` fails boot.
7. **Given** an upload exceeding `MAX_UPLOAD_BYTES`, **then** `413`; **given** a
   file whose content doesn't match its claimed extension, **then** `415`;
   **given** a filename containing `../` or NUL, **then** it is sanitized/rejected
   and never written outside the project's storage area.
8. **Given** `production` with a missing/weak/default `JWT_SECRET`, **then** the
   app refuses to start with a fatal log; **given** a strong secret, it boots.
9. **Given** the compile invocation, **then** shell-escape/`\write18` is disabled
   and a timeout + output/size limit are configured (asserted via the compile
   config/flags), and `docs/` states the trusted-users CE caveat.
10. **Given** a non-member user, **then** they cannot read/write files, compile,
    open the collab WS, or run the agent on another user's project, and IDOR
    attempts return a consistent `403`/`404` without leaking existence.
11. **Given** the `audit` target, **then** it runs `pip-audit` and `npm audit`
    and exits non-zero on a high/critical advisory not in the allowlist.
12. **Given** logs emitted around auth/agent/secret usage, **then** no secret
    (JWT secret, OpenRouter key, DB/Redis creds, password) appears in any log
    line (redaction from spec 51 covers the added keys).

## 8. Test plan

> All tests combined across the project must keep the suite under 2 minutes.
> Rate-limit tests use fakeredis / the shared test Redis; no real network, LLM,
> or large file I/O. Size caps are lowered in the test profile so 413/415 tests
> use tiny payloads.

- **Unit (pytest):**
  - Limiter: window math (allow up to N, block N+1, reset after window) against
    fakeredis; key derivation for `ip`/`user`/`user_or_ip`; fail-open on Redis
    error (patched to raise).
  - Secure-headers middleware: response carries each header with the configured
    value; HSTS toggles with the flag; banner stripped.
  - Upload sanitization: filename normalization (`../`, NUL, absolute paths,
    overlong, charset); extension allow-list; content-sniff mismatch → reject.
  - Validation base: `extra="forbid"` rejects unknown fields; body-size
    middleware computes/aborts correctly (Content-Length and streamed).
  - Secret boot guard: weak/default/missing secret in `production` raises; strong
    passes; dev/test allowed.
  - CORS config builder: rejects `*`+credentials; empty list in prod errors.
- **Integration (pytest + httpx + test DB + fakeredis):**
  - End-to-end 429 on login flood with `Retry-After`; independent compile/agent/
    upload limits; agent composes with spec-49 cost cap.
  - Headers present on 200, 404 and error responses.
  - CORS preflight allowed vs disallowed origin.
  - 413 on oversize body/upload; 415 on type mismatch; traversal filename safely
    handled.
  - Reinforced authz: non-member and `viewer` adversarial cases across files,
    compile, WS, agent return the right status; IDOR consistency.
  - `audit` target invoked in a subprocess returns non-zero against a seeded
    vulnerable pin (or is asserted to call the tools — keep it fast; do not hit
    the network in the fast tier; the real audit runs in CI).
- **E2E (Playwright):** spec 54 smoke-asserts a couple of headers and that a
  rapid auth retry surfaces a 429 in the UI; nothing heavy here.
- **Performance/budget note:** all Redis is faked/local; size limits are tiny in
  tests; no real Tectonic/LLM/network. The dependency audit runs in CI, not in
  the fast suite.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean (`ruff`, `ruff format`, `mypy`/`pyright`).
- [ ] New env vars documented in `.env.example`; security ADR +
      `docs/security-checklist.md` added and every checklist item linked to code
      or a test.
- [ ] Trusted-users compile caveat reaffirmed in `docs/` (and README note).
- [ ] No Overleaf code copied.
