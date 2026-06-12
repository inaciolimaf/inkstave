# Spec 08 — Auth Guards & Sessions (requirements)

## 1. Summary

This spec turns the tokens from spec 07 into reusable **authorization on the
edge of the API**. It provides FastAPI dependencies — `get_current_user`,
`require_admin`, `get_optional_user` — that parse and validate the `Bearer`
access token, load the `User`, and enforce 401/403 semantics; conventions for
marking routes protected; refresh-token reuse/revocation enforcement on
sensitive flows; **rate-limiting groundwork** on the auth endpoints; and a
documented **contract** for how a JWT will authenticate a future WebSocket
connection (used by spec 29). It also adds a single proof endpoint
`GET /api/v1/users/me`.

## 2. Context & dependencies

- **Depends on:** spec **06** (User model + lookup), spec **07** (token
  decode/verify, refresh store, family revocation).
- **Unlocks:** every protected endpoint in Phase 2+ (projects, files, compile,
  history, agent), spec **09** (frontend relies on `401`-on-expiry to trigger
  refresh, and on `/users/me` to hydrate the auth context), and spec **29**
  (implements the WS-auth contract documented here).
- **Affected areas:** backend (dependencies, router, rate-limit middleware/dep),
  docs (WS-auth contract ADR, rate-limit ADR), `.env.example`.

## 3. Goals

- `get_current_user(...)` dependency: extracts `Authorization: Bearer <token>`,
  validates it as an **access** token, loads the `User` from the DB, returns it;
  raises `401` on missing/invalid/expired token or unknown/deleted user.
- `require_admin(...)`: builds on `get_current_user`; raises `403` if
  `is_admin` is false. (Use the DB `is_admin`, not blindly the token claim — see
  §5.2.)
- `get_optional_user(...)`: returns `User | None`; never raises for "no token";
  still raises `401` for a *malformed/expired* token if one is supplied
  (configurable — default: malformed token → 401, absent token → None).
- Clear, consistent `401` vs `403` semantics with a `WWW-Authenticate: Bearer`
  header on `401`.
- Refresh reuse/revocation enforcement remains correct under guard use (the
  guards depend only on access tokens, but the spec verifies that revoked
  families cannot mint usable access tokens via refresh).
- **Rate-limiting groundwork**: a pluggable limiter (Redis-backed, fixed/sliding
  window) applied to `login`, `register`, `refresh` with sane defaults, returning
  `429` with `Retry-After`.
- A documented **WebSocket JWT auth contract** for spec 29.

## 4. Non-goals (explicitly out of scope)

- The live WebSocket server, rooms, presence (spec 28/29) — only the contract.
- Production-grade rate limiting / abuse protection / CAPTCHAs (spec 52).
- Per-resource authorization (project ownership, roles) — that is Phase 2/4
  (specs 11, 33, 34). This spec is about *authentication* guards and the
  admin gate only.
- Frontend (spec 09).
- Server-side HTTP sessions/cookies (Inkstave is token-based; "sessions" here
  means the logical login session represented by a refresh-token family).

## 5. Detailed requirements

### 5.1 Data model

No new tables. Reuses spec-07 Redis refresh store. Rate-limit counters live in
Redis under a separate key namespace, e.g. `ratelimit:{scope}:{identity}` with a
TTL equal to the window.

### 5.2 Backend / API

#### Dependencies (`backend/.../auth/dependencies.py`)

Use FastAPI's `HTTPBearer`/`OAuth2` security scheme (or a custom dependency that
reads the `Authorization` header) — prefer a thin custom dependency so error
shapes match the project's standard error envelope (spec 02).

```python
async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User: ...

async def require_admin(user: User = Depends(get_current_user)) -> User: ...

async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None: ...
```

Behaviour:

- `get_current_user`: no/blank header → `401`. Header present but not `Bearer
  <token>` → `401`. `decode_token(token, "access")` raises → `401`. Token valid
  but `sub` not found in DB → `401` (treat as invalid; do not 404). Returns the
  `User`.
- `require_admin`: load the user via `get_current_user`, then check the
  **database** `user.is_admin` (the `is_admin` claim is a hint/optimisation; the
  authoritative check is the row, so demoting an admin takes effect on the next
  request even with an un-expired token). `False` → `403`.
- `get_optional_user`: absent token → `None`. Present-but-invalid token → `401`
  (default). Present-and-valid → `User`.

Every `401` from these dependencies includes header `WWW-Authenticate: Bearer`.
Bodies follow the project error envelope, e.g.
`{ "detail": "Not authenticated." }` (401, missing/invalid) and
`{ "detail": "Admin privileges required." }` (403).

#### 401 vs 403 semantics (must be consistent)

- **401 Unauthenticated:** no token, malformed token, bad signature, expired
  token, or token references a non-existent user. Means "authenticate (or
  refresh) and retry". Frontend (spec 09) treats `401` as the trigger to call
  `/auth/refresh` once and replay the request.
- **403 Forbidden:** authentication succeeded but the principal lacks the
  required privilege (here: not admin). Means "do not retry as the same user".

#### Proof endpoint

**`GET /api/v1/users/me`** — auth: `get_current_user`.
- Response `200`: `UserPublic` (from spec 06) for the authenticated user.
- `401` if unauthenticated.

(Optional, if trivial) an admin-only ping to exercise `require_admin`, e.g.
**`GET /api/v1/admin/ping`** → `{ "ok": true }` for admins, `403` otherwise.
This is only to test the guard; do not build admin features.

#### Refresh reuse/revocation enforcement (verification, not new behaviour)

No new code beyond spec 07 is strictly required, but this spec must **prove**
that a revoked refresh family cannot be used to obtain access tokens that then
pass `get_current_user`. Add integration tests (see §8) that: log in → use access
on `/users/me` (200) → trigger reuse detection (family revoked) → confirm
`/auth/refresh` returns `401` so no new usable access token is mintable.

#### Rate-limiting groundwork

Provide a reusable, Redis-backed limiter as a FastAPI dependency or middleware:

```python
def rate_limit(scope: str, limit: int, window_seconds: int) -> Depends: ...
```

- Identity = client IP (from the trusted proxy header per spec 02 config) and,
  where available, the submitted email (for `login`/`register`) to throttle
  credential-stuffing per account too. Document the exact key.
- Apply with sane **defaults**:
  - `login`: e.g. 10 attempts / 5 min per IP+email.
  - `register`: e.g. 5 / hour per IP.
  - `refresh`: e.g. 30 / 5 min per IP.
- On exceed: `429 Too Many Requests`, body `{ "detail": "Too many requests." }`,
  header `Retry-After: <seconds>`.
- Must be **fail-open if Redis is unavailable** (log a warning, allow the
  request) so an outage of the limiter cannot lock everyone out — document this
  trade-off; spec 52 may revisit.
- Limits configurable via env (see §5.5). In tests, set high limits by default
  and a dedicated low-limit fixture for the 429 test.

### 5.3 Frontend / UI

None in this spec (spec 09). But this spec **defines the contract** the frontend
relies on: `401` from any protected route is the refresh trigger; `403` is not.

### 5.4 Real-time / jobs / external integrations — WebSocket auth contract (DOCUMENT ONLY)

No WebSocket code is built here. Produce a documented, testable **contract** in
`docs/` that spec 29 will implement:

- **Transport of the token:** the client opens the WS to
  `wss://.../api/v1/ws/projects/{project_id}` and authenticates by sending the
  **access token** in the first message after connect (a `{"type":"auth",
  "token":"<jwt>"}` frame) — *not* in the URL query string (avoids token leakage
  in logs/referrers). Document the rationale. (Browsers cannot set custom headers
  on the WS handshake, hence the first-frame approach; a short-lived
  query-param/subprotocol token is an accepted alternative — pick the first-frame
  approach as the contract and note the alternative.)
- **Validation:** the server validates it exactly like `get_current_user`
  (HS256, `type="access"`, not expired, user exists). On failure: close with WS
  close code `4401` (app-defined "unauthorized"). On success: associate the
  connection with the `user_id` and proceed to room join (spec 29).
- **Expiry during a session:** the access token may expire mid-connection; the
  contract states the client refreshes over HTTP and sends a new `auth` frame to
  re-validate, or the server may permit the existing connection until close
  (spec 29 decides). Document both options; default: re-auth frame required
  within the access TTL or the server closes with `4401`.
- **Authorization (project membership)** is **out of scope** here and belongs to
  spec 34; the contract notes that the WS layer will additionally check project
  access before joining a room.

Provide a tiny pure helper now that spec 29 can reuse, e.g.
`authenticate_ws_token(token, db) -> User` mirroring `get_current_user`'s
validation, **plus a unit test** for it (so the contract is exercised without a
real socket).

### 5.5 Configuration

Add to `.env.example` / `Settings`:

| Var | Default | Purpose |
| --- | --- | --- |
| `RATE_LIMIT_ENABLED` | `true` | Master switch (tests may disable or override). |
| `RATE_LIMIT_LOGIN` | `10/300` | `<limit>/<window_seconds>` for login per IP+email. |
| `RATE_LIMIT_REGISTER` | `5/3600` | register per IP. |
| `RATE_LIMIT_REFRESH` | `30/300` | refresh per IP. |
| `TRUSTED_PROXY_HEADER` | `X-Forwarded-For` | Source of client IP (from spec 02 if already present — reuse, don't duplicate). |
| `WS_AUTH_CLOSE_CODE` | `4401` | (Constant, documented) WS unauthorized close code. |

## 6. Overleaf reference (study only — never copy)

> Read in `../overleaf/` to understand how route-gating and the admin gate work;
> Inkstave implements its own FastAPI dependencies.

- `services/web/app/src/Features/Authentication/AuthenticationController.mjs` —
  the request-gating middleware concepts (how a logged-in check is attached to
  routes and how unauthenticated requests are rejected/redirected). Inkstave
  returns JSON `401`s, not redirects.
- `services/web/app/src/Features/Authorization/AuthorizationMiddleware.mjs` —
  `ensureUserIsLoggedIn` and `ensureUserIsSiteAdmin`: the shape of "must be
  logged in" and "must be admin" gates. Map these to `get_current_user` and
  `require_admin`. (Per-resource gates like project access live in other Overleaf
  middleware and are Inkstave specs 33/34, not here.)
- `services/web/app/src/Features/Authentication/SessionManager.mjs` —
  `isUserLoggedIn` / `getLoggedInUserId`: what "current user" means. Inkstave's
  equivalent is "valid access token → load user".

## 7. Acceptance criteria

1. **Given** a valid access token, **when** I `GET /api/v1/users/me` with
   `Authorization: Bearer <token>`, **then** I get `200` and the `UserPublic` of
   that user.
2. **Given** no `Authorization` header, **when** I call a `get_current_user`-
   protected route, **then** I get `401` with a `WWW-Authenticate: Bearer`
   header.
3. **Given** a malformed, mis-signed, or expired access token, **when** I call a
   protected route, **then** I get `401` (never `403`, never `500`).
4. **Given** a syntactically valid access token whose `sub` user no longer
   exists, **when** I call a protected route, **then** I get `401`.
5. **Given** a non-admin user's valid token, **when** I call a `require_admin`
   route, **then** I get `403` ("Admin privileges required."). **Given** an admin
   user's token, **then** I get `200`.
6. **Given** an admin whose `is_admin` is set to `false` in the DB but who still
   holds an un-expired token claiming `is_admin=true`, **when** they call a
   `require_admin` route, **then** they get `403` (authoritative DB check).
7. **Given** `get_optional_user`, **when** no token is supplied **then** the
   handler runs with `user=None`; **when** an invalid token is supplied **then**
   it returns `401`.
8. **Given** the login rate limit configured low, **when** I exceed it within the
   window, **then** I get `429` with a `Retry-After` header; **and** when Redis is
   made unavailable, the limiter **fails open** (request allowed, warning logged).
9. **Given** a refresh family was revoked by reuse detection (spec 07), **when**
   I try to refresh and then access a protected route, **then** refresh returns
   `401` and I cannot obtain a usable access token.
10. **Given** the WS-auth helper `authenticate_ws_token`, **when** given a valid
    access token it returns the `User`; **when** given an invalid/expired token it
    raises the unauthorized error (the same validation `get_current_user` uses).

## 8. Test plan

> Under the 2-minute budget. Fake Redis for refresh + rate-limit counters;
> crafted-`exp` tokens for expiry; no sleeps.

- **Unit (pytest):**
  - Header parsing: missing, non-Bearer, empty token → mapped to 401 error.
  - `require_admin` DB-authoritative check (token says admin, DB says no → 403).
  - Rate limiter: counter increments, window reset, exceed → 429; fail-open path
    when the Redis client raises.
  - `authenticate_ws_token` valid/invalid/expired.
- **Integration (pytest + httpx + test DB + fake Redis):**
  - `/users/me` with valid token → 200 correct user; no/invalid/expired token →
    401 with `WWW-Authenticate`.
  - admin ping: admin → 200, non-admin → 403.
  - optional-auth route: no token → runs as anonymous; invalid token → 401.
  - login rate limit: loop past the limit → 429 + `Retry-After`.
  - revocation chain: login → /users/me 200 → trigger reuse → refresh 401 →
    confirm no new access token usable.
- **E2E (Playwright):** none this spec.
- **Performance/budget note:** all in-process; rate-limit windows are tiny in
  tests; no network, no real WS, no sleeps.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] New env vars documented in `.env.example`; WS-auth contract ADR and
      rate-limit ADR added under `docs/`.
- [ ] No Overleaf code copied; no server-session model introduced.
