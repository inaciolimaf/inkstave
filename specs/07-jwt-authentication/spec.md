# Spec 07 — JWT Authentication (requirements)

## 1. Summary

This spec adds stateless **access tokens** and stateful **refresh tokens** to
Inkstave. A user logs in with email + password and receives a short-lived signed
JWT access token plus a long-lived refresh token whose server-side record lives
in Redis so it can be **rotated** and **revoked**, with **reuse detection** that
invalidates a whole token family on replay. It exposes `login`, `refresh` and
`logout` endpoints. This is Inkstave's own token design — Overleaf uses sessions
+ Passport and is referenced only for the login/password-check flow.

## 2. Context & dependencies

- **Depends on:** spec **06** (`User` model, `verify_password`). Uses the
  Pydantic `Settings` (spec 02) and async Redis access.
- **Unlocks:** spec **08** (guards verify access tokens; reuse/revocation
  enforcement; WS auth contract), spec **09** (frontend stores access token in
  memory and calls `/refresh` on 401), and every protected endpoint thereafter.
- **Affected areas:** backend (token service, refresh store, schemas, router),
  infra (`.env.example` secrets), docs (ADR).

## 3. Goals

- A token service that **signs** and **verifies** JWTs using **HS256** with a
  server secret (see §5.5 for the recommendation and the secret-rotation note).
- **Access token:** short-lived (default 15 min), carries identity + role claims.
- **Refresh token:** long-lived (default 14 days), opaque-to-client but its
  record is stored server-side in Redis keyed by a `jti`, enabling revocation.
- `POST /api/v1/auth/login` → `{access_token, refresh_token, token_type,
  expires_in}` on valid credentials; uniform `401` on bad email **or** bad
  password (no user-enumeration).
- `POST /api/v1/auth/refresh` → new access + new refresh token (**rotation**);
  the presented refresh token is invalidated. **Reuse detection**: presenting an
  already-rotated/used refresh token revokes the entire token family.
- `POST /api/v1/auth/logout` → revokes the presented refresh token (and,
  optionally, its family).

## 4. Non-goals (explicitly out of scope)

- FastAPI auth dependencies / guards / admin gate (spec 08).
- Rate limiting (spec 08 groundwork; spec 52 hardening).
- WebSocket authentication implementation (spec 29; the *contract* is documented
  in spec 08).
- Frontend (spec 09).
- Email confirmation gating of login, password reset, "remember me" beyond the
  refresh lifetime, MFA.
- Asymmetric (RS256) signing — note it as a future option in the ADR but do not
  build key-pair management now.

## 5. Detailed requirements

### 5.1 Data model

No new SQL tables. Refresh tokens are stored in **Redis** (so revocation is
O(1) and they expire automatically). Define a clear key scheme:

- `refresh:{jti}` → a JSON/hash value:
  `{ "user_id": <uuid>, "family_id": <uuid>, "rotated": <bool>,
     "created_at": <iso>, "expires_at": <iso> }`. Set Redis TTL = refresh
  lifetime so expired tokens self-evict.
- `refresh_family:{family_id}` → a set (or marker) used to revoke an entire
  lineage on reuse detection. On family revocation, delete all member `jti`s or
  mark the family revoked and reject any member.

Each successful login creates a **new family** (`family_id = uuid4`). Each
refresh keeps the same `family_id`, mints a new `jti`, and marks the old `jti`
as `rotated=true` (do not delete it immediately — keep it briefly so a replay of
the *old* token is detectable as reuse; or store a `used` marker. Keeping the
old `jti` until family revocation or TTL is simplest).

> If the team prefers a DB table over Redis for durability, a `refresh_tokens`
> table (`jti UUID PK`, `user_id FK`, `family_id UUID`, `rotated bool`,
> `revoked bool`, `expires_at timestamptz`, `created_at`) is an acceptable
> alternative — but Redis is the default per `CLAUDE.md` (Redis is the
> cache/queue layer and TTL-based eviction fits refresh tokens). Pick one,
> document it; the endpoint contracts below are identical either way.

### 5.2 Token format & claims

Use the `python-jose[cryptography]` or `PyJWT` library (pick one; PyJWT is
lighter). All tokens are JWTs signed HS256 with `JWT_SECRET`.

**Access token claims:**

| Claim | Meaning |
| --- | --- |
| `sub` | user id (UUID string) |
| `type` | `"access"` |
| `is_admin` | bool (copied from the user; convenience for guards) |
| `iat` | issued-at (epoch) |
| `exp` | expiry (epoch) = `iat + ACCESS_TOKEN_TTL` |
| `jti` | unique token id (uuid4) |

**Refresh token claims:**

| Claim | Meaning |
| --- | --- |
| `sub` | user id |
| `type` | `"refresh"` |
| `family_id` | token-family UUID |
| `jti` | this refresh token's id (matches the Redis key) |
| `iat`, `exp` | issued/expiry (`exp = iat + REFRESH_TOKEN_TTL`) |

Verification must check signature, `exp`, and `type` (reject an access token
where a refresh token is expected and vice-versa). A helper `decode_token(token,
expected_type)` returns the claims or raises a typed `TokenError`.

### 5.3 Backend / API

Token service module (e.g. `backend/.../auth/tokens.py`):

```python
def create_access_token(user: User) -> tuple[str, int]:  # (token, expires_in_seconds)
def create_refresh_token(user_id: UUID, family_id: UUID) -> tuple[str, str]:  # (token, jti)
def decode_token(token: str, expected_type: Literal["access","refresh"]) -> Claims: ...
```

Refresh store module (e.g. `backend/.../auth/refresh_store.py`) using async
Redis:

```python
async def store_refresh(jti, user_id, family_id, expires_at) -> None
async def get_refresh(jti) -> RefreshRecord | None
async def rotate_refresh(old_jti) -> None      # mark old rotated/used
async def revoke_family(family_id) -> None      # reuse detection / logout-all
async def is_member_valid(jti) -> bool
```

#### Schemas (Pydantic v2)

`LoginRequest`: `{ email: EmailStr, password: str }`.

`TokenPair` (response): `{ access_token: str, refresh_token: str,
token_type: "bearer", expires_in: int }` (`expires_in` = access TTL seconds).

`RefreshRequest`: `{ refresh_token: str }`.

`LogoutRequest`: `{ refresh_token: str }`.

`MessageResponse`: `{ detail: str }`.

> Refresh/logout take the refresh token in the JSON body for this spec (the
> frontend spec 09 will store it appropriately; whether it ultimately rides in an
> httpOnly cookie is a spec-09 decision — keep the backend body-based and simple,
> and note the cookie option in the ADR).

#### Endpoints

**`POST /api/v1/auth/login`** — auth: none.
- Request: `LoginRequest`. Response: `200` `TokenPair`.
- Flow: look up user by normalised email; **always** run `verify_password`
  against either the stored hash or a dummy hash (constant-time, to avoid timing
  enumeration) — if user missing, still perform a hash verification against a
  fixed dummy argon2 hash, then fail. On success: create `family_id`, mint access
  + refresh, store refresh in Redis, return the pair.
- Errors: invalid email **or** password → `401` `{ "detail": "Invalid email or
  password." }` (identical message for both). Malformed body → `422`.

**`POST /api/v1/auth/refresh`** — auth: none (the refresh token *is* the auth).
- Request: `RefreshRequest`. Response: `200` `TokenPair` (new access + new
  refresh).
- Flow: decode token (`expected_type="refresh"`); look up `refresh:{jti}`.
  - If record missing/expired → `401`.
  - If record exists and is **not** rotated/used → rotate (mark old used), mint a
    new refresh in the same family, store it, return new pair.
  - If record exists but is **already rotated/used** → **reuse detected**:
    `revoke_family(family_id)` and return `401` `{ "detail": "Refresh token
    reuse detected; session revoked." }`.
  - If the family is already revoked → `401`.
- Errors: bad signature / wrong `type` / expired → `401`.

**`POST /api/v1/auth/logout`** — auth: none required to *present* a refresh
token; (spec 08 may additionally accept the access token to identify the user).
- Request: `LogoutRequest`. Response: `200` `MessageResponse`
  `{ "detail": "Logged out." }`.
- Flow: decode the refresh token; if valid, revoke it (and its family, to log
  the device fully out). **Idempotent**: an already-revoked/unknown token still
  returns `200` (do not leak validity). Malformed/missing token → `422`.

#### Status-code summary

| Endpoint | Success | Auth/credential failure | Validation |
| --- | --- | --- | --- |
| login | 200 | 401 (uniform) | 422 |
| refresh | 200 | 401 (missing/expired/reuse/revoked) | 422 |
| logout | 200 (idempotent) | — | 422 |

### 5.4 Real-time / jobs / external integrations

None. Redis is used synchronously-async for the refresh store; no ARQ job. The
WebSocket auth *contract* (how a future WS connection presents the access token)
is **documented in spec 08**, not here.

### 5.5 Configuration

Add to `.env.example` and `Settings`:

| Var | Default | Purpose |
| --- | --- | --- |
| `JWT_SECRET` | (no default; required, ≥32 random bytes) | HS256 signing secret. |
| `JWT_ALGORITHM` | `HS256` | Signing alg. Document RS256 as a future option. |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` (15 min) | Access token lifetime. |
| `REFRESH_TOKEN_TTL_SECONDS` | `1209600` (14 days) | Refresh token lifetime / Redis TTL. |
| `JWT_ISSUER` | `inkstave` | `iss` claim (optional but recommended). |

**Recommendation:** **HS256 with a strong `JWT_SECRET`** for now — simplest and
sufficient for a single-service deployer. **Secret-rotation note for the ADR:**
to rotate `JWT_SECRET` without invalidating everyone instantly, support an
optional list of *previous* secrets accepted for *verification only* (e.g.
`JWT_SECRET_PREVIOUS`), while always signing with the current secret; old access
tokens expire quickly (15 min) and refresh tokens are server-side revocable, so
rotation impact is bounded. Implementing the previous-secret list is optional in
this spec but must be designed-for (don't hard-code a single key in a way that
blocks it).

## 6. Overleaf reference (study only — never copy)

> Overleaf uses **server sessions + Passport**, *not* JWT. Study only the
> login/password-check flow; ignore its session machinery.

- `services/web/app/src/Features/Authentication/AuthenticationController.mjs` —
  the login entry flow: read credentials, attempt auth, uniform failure handling.
  (`passportLogin`, `doPassportLogin`, `_doPassportLogin`.)
- `services/web/app/src/Features/Authentication/AuthenticationManager.mjs` —
  `authenticate`/password-compare: looks up the user, runs `bcrypt.compare`, and
  the *same failure path* for unknown email vs. wrong password. Learn the
  constant-time-against-enumeration intent; Inkstave reuses argon2
  `verify_password` from spec 06 plus a dummy-hash compare for missing users.
- `services/web/app/src/Features/Authentication/SessionManager.mjs` — how
  Overleaf models "who is logged in" via the session. **Reference only** to
  understand what claims/identity our access token must carry; we do **not**
  build sessions.

## 7. Acceptance criteria

1. **Given** a registered user, **when** they `POST /auth/login` with correct
   credentials, **then** they get `200` and a `TokenPair` with a `bearer`
   `token_type`, a non-empty access + refresh token, and `expires_in` equal to
   the configured access TTL.
2. **Given** the returned access token, **when** it is decoded with `JWT_SECRET`,
   **then** it has `type="access"`, `sub` = the user id, `is_admin` matching the
   user, and an `exp` ≈ `iat + ACCESS_TOKEN_TTL`.
3. **Given** a wrong password **or** an email that does not exist, **when**
   `POST /auth/login`, **then** the response is `401` with the **identical**
   message `"Invalid email or password."` in both cases, and the response timing
   does not trivially distinguish the two (a dummy hash compare runs for the
   missing-user case).
4. **Given** a valid refresh token, **when** `POST /auth/refresh`, **then** the
   response is `200` with a **new** access token and a **new** refresh token
   (different `jti`), the old refresh token is now invalid, and the new refresh
   token works on a subsequent refresh.
5. **Given** a refresh token that has already been rotated (used once), **when**
   it is presented again to `POST /auth/refresh`, **then** the response is `401`
   ("reuse detected"), **and** the most-recently issued refresh token in that
   family is now **also** rejected (the whole family is revoked).
6. **Given** an expired or tampered refresh token, **when** `POST /auth/refresh`,
   **then** the response is `401` and no new tokens are issued.
7. **Given** a valid refresh token, **when** `POST /auth/logout`, **then** the
   response is `200`, and a subsequent `POST /auth/refresh` with that token (or
   any token in its family) returns `401`. Calling logout again is still `200`
   (idempotent).
8. **Given** any malformed request body (missing field, non-string token),
   **then** the endpoint returns `422` and changes no server state.

## 8. Test plan

> Under the 2-minute budget. Use a fake/in-memory Redis (e.g. `fakeredis`) or a
> dedicated test Redis; argon2 cost stays minimal via spec-06 test overrides. No
> real time waits — drive expiry by signing tokens with a past `exp` or by
> patching the clock, not by sleeping.

- **Unit (pytest):**
  - Token service: round-trip encode/decode; `decode_token` rejects wrong
    `type`, bad signature, and expired `exp`; access vs refresh claim sets.
  - Refresh store: store→get; rotate marks used; `revoke_family` invalidates all
    members; `is_member_valid` semantics.
- **Integration (pytest + httpx + test DB + fake Redis):**
  - Login happy path → `200` + valid `TokenPair`; claims assertion.
  - Login wrong password and unknown email → both `401`, identical body.
  - Refresh rotation: refresh once → new pair; old token now `401`.
  - Reuse detection: replay an old (rotated) refresh → `401` + family revoked
    (verify the latest family token is also rejected).
  - Expired refresh (sign with past `exp`) → `401`.
  - Logout → `200`; subsequent refresh `401`; second logout `200` (idempotent).
  - Validation: malformed bodies → `422`.
- **E2E (Playwright):** none this spec.
- **Performance/budget note:** no sleeps; expiry simulated via crafted `exp` or
  monkeypatched `datetime`; fake Redis keeps it in-process; argon2 minimal cost.

## 9. Definition of Done

- [ ] All requirements in §5 implemented.
- [ ] All acceptance criteria in §7 pass.
- [ ] All tests in §8 written and green.
- [ ] Full suite runs in < 2 minutes.
- [ ] Lint/format/type-check clean.
- [ ] `JWT_SECRET` and the TTL/issuer vars documented in `.env.example`; token
      model ADR (HS256, lifetimes, rotation, reuse detection, secret rotation)
      added under `docs/`.
- [ ] No Overleaf code copied; no session/Passport model replicated.
