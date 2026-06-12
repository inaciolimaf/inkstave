# ADR 0007 — Auth guards, the WebSocket auth contract, and rate limiting

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 08 — Auth Guards & Sessions

## Context

Spec 07 issued tokens; spec 08 turns them into reusable authorization at the
edge of the API, documents how a future WebSocket will authenticate, and lays
the groundwork for rate limiting.

## Decisions

### 1. Three guards with strict 401 vs 403 semantics

- `get_current_user` — reads `Authorization: Bearer <token>`, validates it as an
  **access** token, loads the `User` from the DB, returns it. Missing/blank
  header, non-Bearer, malformed/mis-signed/expired token, or a `sub` with no DB
  row → **401**.
- `require_admin` — builds on `get_current_user` and checks the **database**
  `user.is_admin`, not the token claim. The `is_admin` claim is only a hint, so
  demoting an admin takes effect on their **next request** even with an
  un-expired token. Not admin → **403**.
- `get_optional_user` — returns `None` when no token is sent (route runs
  anonymously); a token that is *present but invalid* still → **401**.

**401 vs 403 is a public contract** the frontend (spec 09) depends on:

- **401** = "authenticate or refresh and retry" — the SPA calls `/auth/refresh`
  once and replays the request. Every 401 carries `WWW-Authenticate: Bearer`.
- **403** = "authenticated but not permitted" — do **not** retry as the same
  user.

We use FastAPI's `HTTPBearer(auto_error=False)` and emit the project's uniform
error envelope (spec 02) rather than FastAPI's default `{"detail": ...}`, keeping
the error shape consistent (per ADR 0005). The 401/429 responses attach extra
headers (`WWW-Authenticate`, `Retry-After`) via an optional `headers` field on
`AppError`.

### 2. WebSocket JWT auth contract (documented; implemented in spec 29)

No WebSocket code is built here. The contract spec 29 will implement:

- **Transport:** the client opens `wss://.../api/v1/ws/projects/{project_id}` and
  authenticates by sending the access token in the **first frame after connect**:
  `{"type":"auth","token":"<jwt>"}`. The token is **not** put in the URL query
  string — that would leak it into server logs, proxies and `Referer` headers.
  (Browsers cannot set custom headers on the WS handshake, which is why a header
  cannot be used; a short-lived query-param or `Sec-WebSocket-Protocol` token is
  an accepted alternative, but the first-frame approach is the chosen contract.)
- **Validation:** the server validates the token **exactly like
  `get_current_user`** — HS256, `type="access"`, not expired, user exists — via
  the shared `authenticate_ws_token(token, token_service, session)` helper
  (unit-tested here, so the contract is exercised without a real socket). On
  failure the server closes with WS close code **`4401`** (`WS_AUTH_CLOSE_CODE`,
  an app-defined "unauthorized"). On success the connection is associated with
  the `user_id` and proceeds to room join.
- **Expiry mid-session:** the access token may expire during a long-lived
  connection. **Default contract:** the client refreshes over HTTP and sends a
  new `auth` frame within the access TTL; otherwise the server closes with
  `4401`. (Spec 29 may instead permit the existing connection until close — both
  options are documented; the re-auth-frame default is the safer one.)
- **Project authorization** (membership/roles) is **out of scope** here — the WS
  layer will additionally check project access before joining a room (spec 34).

### 3. Rate-limiting groundwork (fail-open)

- A Redis-backed **fixed-window** limiter exposed as a `rate_limit(scope)`
  FastAPI dependency, applied to `login`, `register`, `refresh`.
- **Identity / key:** `ratelimit:{scope}:{identity}` where `identity` is the
  client IP (from `TRUSTED_PROXY_HEADER`, default `X-Forwarded-For`, first hop)
  and — for `login`/`register` — additionally the submitted email
  (`{ip}:{email}`), to throttle credential stuffing per account. The counter's
  Redis key TTL equals the window, so it self-resets.
- **Defaults** (configurable via env): `login` 10/5min (per IP+email),
  `register` 5/hour (per IP), `refresh` 30/5min (per IP).
- **Exceed → `429`** with body `{"error":{"type":"rate_limited",...}}` and a
  `Retry-After` header (remaining window seconds).
- **Fail-open:** if Redis errors, the limiter **logs a warning and allows the
  request**. A limiter outage must never lock everyone out. This is a deliberate
  availability-over-strictness trade-off; spec 52 may revisit (e.g. a sliding
  window, local fallback counters, or fail-closed for the most sensitive scopes).

## Consequences

- New endpoints: `GET /api/v1/users/me` (proof of `get_current_user`) and
  `GET /api/v1/admin/ping` (proof of `require_admin`).
- `AppError` gained an optional `headers` field; `UnauthorizedError` defaults it
  to `WWW-Authenticate: Bearer`; `RateLimitError` sets `Retry-After`.
- New settings/env: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_LOGIN`,
  `RATE_LIMIT_REGISTER`, `RATE_LIMIT_REFRESH`, `TRUSTED_PROXY_HEADER`,
  `WS_AUTH_CLOSE_CODE`.
- Spec 29 implements the WS contract; spec 34 adds per-project authorization;
  spec 52 hardens rate limiting.

## Alternatives considered

- **Token in WS URL query string** — simplest, but leaks the token into logs and
  `Referer`; rejected in favour of a first-frame `auth` message.
- **Trusting the `is_admin` claim for the admin gate** — faster (no DB read) but
  cannot reflect a mid-token demotion; rejected for an authoritative DB check.
- **Fail-closed rate limiting** — safer against abuse but turns a Redis blip into
  a full outage; rejected (fail-open) for availability, revisited in spec 52.
- **`slowapi`/third-party limiter** — heavier and opinionated; a tiny
  Redis-`INCR` window suffices for the groundwork.
