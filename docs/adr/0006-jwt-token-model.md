# ADR 0006 — JWT token model: HS256, lifetimes, rotation, reuse detection

- **Status:** Accepted
- **Date:** 2026-06-09
- **Context spec:** 07 — JWT Authentication

## Context

Inkstave needs its own authentication tokens (Overleaf uses server sessions +
Passport, which we do not replicate). The design must be stateless enough to
scale, yet support revocation and detect refresh-token theft.

## Decisions

### 1. Stateless access + stateful refresh

- **Access token:** a stateless JWT, short-lived (`ACCESS_TOKEN_TTL_SECONDS`,
  default 900s = 15 min). Claims: `sub` (user id), `type="access"`, `is_admin`
  (convenience for the spec-08 guards), `iat`, `exp`, `jti`, `iss`.
- **Refresh token:** a long-lived JWT (`REFRESH_TOKEN_TTL_SECONDS`, default 14
  days) whose **server-side record lives in Redis**, so it is revocable. Claims:
  `sub`, `type="refresh"`, `family_id`, `jti`, `iat`, `exp`, `iss`.
- Decoding always validates signature, `exp`, `iss`, the required claim set, and
  that `type` matches what the caller expects (an access token cannot be used
  where a refresh token is required and vice-versa).

### 2. Signing: HS256 with a rotatable secret

- **HS256** with a strong `JWT_SECRET` — simplest and sufficient for a
  single-service deployment. **RS256** (asymmetric) is noted as a future option
  if token verification ever needs to be delegated to other services; key-pair
  management is intentionally not built now.
- **Secret rotation is designed-for:** the service signs with the current
  `JWT_SECRET` but verifies against the current secret **and** an optional list
  of retired secrets (`JWT_SECRET_PREVIOUS`). To rotate, move the old secret into
  `JWT_SECRET_PREVIOUS`, set a new `JWT_SECRET`; old access tokens expire within
  15 minutes and refresh tokens are server-side revocable, so impact is bounded.
- `JWT_SECRET` is a **required** setting (no default) so the app fails fast if it
  is unset.

### 3. Refresh storage in Redis (not a DB table)

Per `CLAUDE.md`, Redis is the cache/queue layer and TTL-based eviction fits
refresh tokens perfectly. Keys:

- `refresh:{jti}` → JSON `{user_id, family_id, rotated, created_at, expires_at}`,
  with Redis TTL = refresh lifetime (records self-evict on expiry).
- `refresh_family_revoked:{family_id}` → a marker that outlives its members and
  invalidates the whole lineage.

A DB `refresh_tokens` table was an acceptable alternative (more durable); Redis
was chosen for O(1) revocation and automatic expiry. The endpoint contracts are
identical either way.

### 4. Rotation + reuse detection (family revocation)

- Each **login** starts a new **family** (`family_id = uuid4`).
- Each **refresh** rotates: the presented token's record is marked `rotated`, a
  new token (new `jti`, same `family_id`) is issued, and the user is re-loaded
  from the DB so `is_admin` on the new access token is always current.
- **Reuse detection:** presenting an already-`rotated` token is a replay (the
  token was stolen or leaked). The entire **family is revoked** and the request
  fails `401`. This means a thief and the legitimate user cannot both keep
  refreshing — the next action by either kills the session, which is the desired
  theft-mitigation property.
- **Logout** revokes the token's family (full device logout) and is
  **idempotent**: unknown/invalid tokens still return `200`, leaking nothing.

### 5. Login is non-enumerating

`POST /auth/login` returns the **same** `401` "Invalid email or password." for a
wrong password and an unknown email. For a missing user we still run a
`verify_password` against a fixed **dummy argon2 hash**, so a missing user is not
detectably faster than a wrong password (timing parity).

### 6. Tokens in the JSON body (for now)

`refresh`/`logout` take the refresh token in the JSON body. Whether the refresh
token ultimately rides in an **httpOnly cookie** is a spec-09 (frontend)
decision; the backend stays body-based and simple. Error responses use the
project's uniform error envelope (spec 02), consistent with ADR 0005.

## Consequences

- New runtime dep: `pyjwt`.
- New settings/env: `JWT_SECRET` (required), `JWT_SECRET_PREVIOUS`,
  `JWT_ALGORITHM`, `JWT_ISSUER`, `ACCESS_TOKEN_TTL_SECONDS`,
  `REFRESH_TOKEN_TTL_SECONDS`.
- The pydantic mypy plugin was enabled so a required-from-env setting
  (`jwt_secret`) does not appear as a mandatory constructor argument.
- Spec 08 consumes access tokens in `get_current_user`/`require_admin` and
  documents the WebSocket auth contract.

## Alternatives considered

- **Server sessions (Overleaf's model)** — stateful, doesn't fit a token-based
  SPA + future WS auth; rejected.
- **RS256 now** — unnecessary key management for a single service; deferred.
- **Stateless refresh (no server record)** — cannot revoke or detect reuse;
  rejected. The Redis record is what enables both.
- **DB table for refresh tokens** — viable; Redis chosen for TTL eviction and
  O(1) revocation.
