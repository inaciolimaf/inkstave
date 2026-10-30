# ADR 0107 — Session revocation reaches access tokens

**Status:** accepted · **Phase:** 7 — Hardening, packaging & docs

## Context

ADR 0006 made refresh tokens revocable, but an access token kept working until it
expired: after a logout or a password change, a copied token had up to
`ACCESS_TOKEN_TTL_SECONDS` left.

## Decision

Every token path runs one check, `is_alive` in `modules/auth/credentials/sessions.py`:
the HTTP guards, the SSE dependency, the WebSocket admission and the refresh route.

- **`sv`** carries `users.session_version`. A password change, a password reset and a
  deactivation move it, which ends every session of the account.
- **`sid`** is the refresh family id, copied into the access token. Logout writes it to
  `revoked_sessions`, so one device leaves and the others stay in. Rows live for the
  refresh lifetime and are swept on each logout.
- **`users.is_active`** is new: the project only had hard deletion. It is set by
  `inkstave deactivate-user --email`. There is no route and no reactivation command;
  undoing one is `UPDATE users SET is_active = true`.

The check costs one primary-key lookup per request, next to the user's. Postgres rather
than Redis, so a Redis outage or flush cannot bring a revoked session back.

## Tokens issued before this change

A deploy signs nobody out. A missing `sv` counts as 0, every account's starting version,
so an old token lives on until the account's version moves. An old refresh token already
has `family_id`, and rotating it yields tokens with both claims. An old access token has
no `sid`, so a logout cannot reach it: it dies on its own within
`ACCESS_TOKEN_TTL_SECONDS` (15 minutes by default). A password change or deactivation
does reach it, because the version moves past 0.

## Limits

- A WebSocket or SSE stream is checked when it opens. One already open survives until it
  disconnects.
- Refresh-token reuse revokes the family in Redis only, not `sid`: that path raises, and
  the unit of work would undo the write. The access token dies when it expires.
