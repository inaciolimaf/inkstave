# Inkstave Security Checklist (spec 52)

The review gate. Each item links to the code and/or test that proves it.

## Transport / headers
- [x] CSP on every response — `security/headers.py`; `test_security_api.py::test_security_headers_present_on_404_and_200`
- [x] `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP — same
- [x] HSTS only when `HSTS_ENABLED=true` (off in dev/test) — `security/headers.py`
- [x] Server / `X-Powered-By` banner removed — `headers.py`; header test asserts absence
- [x] PDF output sets `Content-Type: application/pdf` + sanitized `Content-Disposition` — `api/routes/compile.py::_pdf_headers`, `api/routes/files.py::_sanitize_header_filename`

## AuthN / AuthZ
- [x] `JWT_SECRET` strength + boot guard in production — `config.py::_guard_production_secret`; `test_security.py::test_production_secret_guard`
- [x] Refresh-token rotation — spec 07/08 (`auth/`)
- [x] Authz on every project resource incl. WS + compile — `authorization/`, `collab/ws/router.py::_authorize`; `test_authz_guard_coverage.py`
- [x] No IDOR / existence leak (consistent 403/404) — agent `_owned_session` returns 404; `test_authz_guard_coverage.py`

## Rate limiting
- [x] Auth / compile / agent / upload policies present — `security/rate_limit.py`, route `dependencies=[...]`
- [x] 429 + `Retry-After` + `X-RateLimit-Remaining: 0` — `errors.py::RateLimitError`; `test_security_api.py::test_rate_limit_dependency_sets_headers_and_429s`
- [x] Fail-open documented + metric — `rate_limit.py::_enforce`; `test_rate_limit_fails_open_when_redis_errors`
- [x] Agent composes with spec-49 cost cap — `agent/api/jobs.py` (both must pass)

## Input
- [x] Pydantic `extra="forbid"` base — `schemas/base.py::StrictModel`; `test_security_api.py::test_extra_field_is_rejected_422`
- [x] Length/size caps on free-text + collections — field `max_length`/`Query(..., le=)`
- [x] Body-size middleware (413) — `security/body_limit.py`; `test_body_size_limit_returns_413`
- [x] Typed path params (UUID) → 422 not 500 — FastAPI route signatures

## Uploads
- [x] Per-file size cap (413, streamed) — `services/file_service.py`
- [x] Extension allow-list + content sniff + extension↔content match (415) — `security/uploads.py`; `test_files_api.py::test_upload_content_extension_mismatch_is_415`
- [x] Filename normalization (`../`, NUL, absolute, charset, length) — `uploads.py::sanitize_filename`; `test_security.py`, `test_upload_traversal_filename_is_sanitized_and_stored_safely`
- [ ] SVG/EPS are binary assets; the **frontend** must render them as images or sanitize (SVG can carry scripts) — operator/UI note

## CORS
- [x] Explicit allow-list, never `*`+credentials, empty in prod fails boot — `config.py::_guard_production_cors`; `test_security.py::test_cors_guard_rejects_wildcard_and_empty_prod`, `test_security_api.py::test_cors_preflight_allows_configured_origin`

## Compile sandbox
- [x] **Per-compile gVisor isolation for public multi-tenant use** (spec 105) — `COMPILE_RUNNER=sandbox` runs each compile in a throwaway `runsc` container: `--runtime=runsc --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534` + hard `--memory/--pids-limit/--cpus/--tmpfs` caps — `compile/runner.py::SandboxedTectonicRunner`; `test_compile_sandbox_runner.py`
- [x] No user-controlled data in the docker argv — fixed argv via `create_subprocess_exec` (no shell); `main_file` validated — `runner.py::validate_main_file`; `test_compile_sandbox_runner.py::test_*filename*`
- [x] Daily anti-DoS compile quota (30/user/24h → 429 + Retry-After) + per-user concurrency cap — `security/rate_limit.py` (`compile_daily` policy), `compile/coordinator.py`; `test_compile_daily_quota.py`
- [x] Shell-escape / `\write18` off — Tectonic has no such flag; `test_compile_runner.py::test_compile_sandbox_no_shell_escape_no_inherited_secrets`
- [x] Timeout + output/size limit — `compile/runner.py` (timeout_s → `docker kill`), spec 21
- [x] No inherited secrets in the compile env — `runner.py::build_command` (minimal allow-listed env); same test + `test_compile_sandbox_runner.py`
- [x] Temp workdir per compile, cleaned up — `compile/jobs.py` (cleanup backstop)
- [x] Network egress blocked in sandbox mode (`--network none`) + pinned, prewarmed package set (`--only-cached`) — `infra/tectonic/Dockerfile`, spec 21
- [x] `docker.sock` only on the worker, fronted by a docker-socket-proxy (create/start/wait/kill/rm) — `infra/README.md`

## Secrets
- [x] Env-only, never logged (redacted) — spec 51 `observability/log.py::redact` covers `secret`/`api_key`/`authorization`
- [x] Rotation guidance — below

## Dependencies
- [x] `pip-audit` + `npm audit --audit-level=high` gate — `scripts/audit.sh`; runs in CI (spec 57)
- [x] Lockfiles pinned (`uv.lock`, `package-lock.json`); review cadence: weekly

---

## Sandboxed compiles — two postures (spec 105)

Inkstave supports two compile postures, selected by `COMPILE_RUNNER`:

- **`local` (default).** Tectonic runs in-process with process-level hardening
  (no shell-escape, a per-compile working directory that is cleaned up, a CPU
  timeout and output cap, and a **minimal environment with no application
  secrets**). Suitable when **all users of an instance trust each other**
  (single-team / single-tenant).
- **`sandbox` (public multi-tenant).** Every compile runs in a **throwaway
  gVisor (`runsc`) container** with `--network none`, a read-only root, all Linux
  capabilities dropped, `no-new-privileges`, a non-root user (`65534`), and hard
  container-enforced memory / PID / CPU / tmpfs caps. The project is mounted
  read-only; outputs go to a separate mount; the timeout/cancel path
  `docker kill`s the container. Abuse is bounded by a **daily compile quota**
  (30/user/24h) plus the per-user concurrency cap. This makes Inkstave safe to
  operate for **public, mutually-untrusted** users. See `infra/README.md` for the
  gVisor install, the offline `inkstave-tectonic` image, and the hardened
  (worker-only, socket-proxied) Docker daemon access.

### Threat model (public `sandbox` mode)

| Risk | Disposition |
| --- | --- |
| **gVisor (`runsc`) escape** | Accepted residual risk; keep `runsc` patched, isolate the worker host/VM, and rely on `--network none` so an escapee still has no egress. |
| **DoS / abuse** | Covered: container `--memory`/`--cpus`/`--pids-limit`/tmpfs caps, wall-clock timeout (→ `docker kill`), spec-21 output/log caps, per-user concurrency cap, and the daily quota (→ 429). |
| **Argument injection into `docker`** | Covered: fixed argv via `create_subprocess_exec` (no shell); `main_file` validated (no `..`, no leading `-`, conservative charset); file names/contents live only inside the read-only mount. |
| **Secret exfiltration via compile env** | Covered: the container inherits no app env (only `PATH`/`HOME` reach the launcher), and `--network none` blocks egress regardless. |
| **XSS via SVG/EPS/PDF output** | **Open** (frontend render/sanitisation item below); `--network none --only-cached` limits the blast radius (no remote asset fetch). |
| **AuthZ / IDOR** | Covered by prior specs (34/52); unchanged here. |
| **Agent network egress** | Covered: agent tools never reach the network; an egress-lock test (`test_agent_egress_lock.py`) guards against regressions. |
| **Docker daemon abuse** | Covered operationally: `docker.sock` only on the worker, fronted by a docker-socket-proxy restricted to container create/start/wait/kill/rm. |
| **Supply chain** | Covered by prior specs: `pip-audit`/`npm audit` gate, pinned lockfiles, pinned Tectonic bundle/package set. |

## Secret rotation (operator steps)

- **JWT_SECRET:** generate a new ≥32-byte random value; to rotate without logging
  everyone out, set the new value as `JWT_SECRET` and the old one in
  `JWT_SECRET_PREVIOUS` (verification accepts both during the overlap), then drop the
  previous after the access-token TTL. Rotating without overlap invalidates all
  outstanding tokens.
- **OPENROUTER_API_KEY / DB / Redis creds:** rotate at the provider, update the env,
  restart. Secrets are never written to logs (spec-51 redaction; the spec-55 pass
  also added `access_key` to the denylist so `s3_access_key_id` is redacted).

## Spec-55 hardening notes

- **Rate limiting:** the auth limiter increments its window counter and sets the TTL
  in a single atomic Lua call (no counter can be left without an expiry). The client
  IP honours `X-Forwarded-For` **only** when `trust_proxy_headers` is enabled — keep
  it off unless Inkstave sits behind a trusted proxy, or per-IP limits can be spoofed.
- **Request validation:** every request **body** model now extends `StrictModel`
  (`extra="forbid"`), so unknown fields are rejected (422) — closing the request-
  smuggling class. A guard-coverage test (`test_hardening_55`) asserts every sensitive
  route carries a rate-limit policy and that secure headers appear on error responses.
